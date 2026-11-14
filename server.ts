import 'dotenv/config';
import crypto from 'node:crypto';
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import express, { type Request, type Response } from 'express';
import { GoogleGenAI } from '@google/genai';
import { z } from 'zod';

const PORT = Number(process.env.PORT || 3000);
const DB_PATH = path.resolve(process.env.SQLITE_DB_PATH || './database/retail_connect.sqlite');
const JWT_SECRET = process.env.JWT_SECRET || 'dev-stage1-retail-connect-secret';

function ensureDatabaseSeeded(): DatabaseSync {
  if (!fs.existsSync(DB_PATH)) {
    console.log('SQLite database not found; running deterministic synthetic seeder (SEED=42)...');
    execSync('python3 database/seed/generate_synthetic_data.py', { stdio: 'inherit' });
  }
  const db = new DatabaseSync(DB_PATH);
  db.exec('PRAGMA foreign_keys = ON;');
  return db;
}

const db = ensureDatabaseSeeded();

function hashPassword(raw: string): string {
  return crypto.createHash('sha256').update(`retail_connect_salt::${raw}`).digest('hex');
}

function signToken(payload: { sub: string; email: string; role: string }): string {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const body = Buffer.from(
    JSON.stringify({ ...payload, exp: Math.floor(Date.now() / 1000) + 86400 }),
  ).toString('base64url');
  const sig = crypto.createHmac('sha256', JWT_SECRET).update(`${header}.${body}`).digest('base64url');
  return `${header}.${body}.${sig}`;
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return Math.round(2 * R * Math.asin(Math.sqrt(a)) * 1000) / 1000;
}

export function createApp() {
  const app = express();
  app.use(express.json({ limit: '5mb' }));

  const TABLE_NAMES = [
    'users',
    'stores',
    'products',
    'product_images',
    'product_aliases',
    'suppliers',
    'store_inventory',
    'stock_batches',
    'sales',
    'demand_forecasts',
    'reorder_suggestions',
    'pricing_recommendations',
    'price_history',
    'competitor_prices',
    'agent_runs',
    'inventory_image_uploads',
    'detected_products',
    'owner_approvals',
  ];

  // Health & Database Foundation Check
  app.get('/api/v1/health', (_req: Request, res: Response) => {
    const tableCounts: Record<string, number> = {};
    for (const tbl of TABLE_NAMES) {
      const row = db.prepare(`SELECT COUNT(*) AS cnt FROM ${tbl}`).get() as { cnt: number };
      tableCounts[tbl] = row.cnt;
    }
    res.json({
      status: 'ok',
      service: 'retail-connect-api',
      stage: 'stage-1-foundation',
      database_engine: 'sqlite-local-mirror (PostgreSQL/Supabase DDL ready)',
      database_connected: true,
      synthetic_seed: Number(process.env.SYNTHETIC_SEED || 42),
      gemini_configured: Boolean(
        process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY !== 'MY_GEMINI_API_KEY',
      ),
      timestamp_utc: new Date().toISOString(),
      table_counts: tableCounts,
    });
  });

  // Auth: Login
  const loginSchema = z.object({
    email: z.string().email(),
    password: z.string().min(6),
  });

  app.post('/api/v1/auth/login', (req: Request, res: Response) => {
    const parsed = loginSchema.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: 'Invalid credentials format', details: parsed.error.flatten() });
      return;
    }
    const { email, password } = parsed.data;
    const user = db
      .prepare('SELECT id, email, password_hash, full_name, phone, role, preferred_language, is_synthetic FROM users WHERE email = ? AND is_active = 1')
      .get(email.toLowerCase()) as
      | {
          id: string;
          email: string;
          password_hash: string;
          full_name: string;
          phone: string | null;
          role: string;
          preferred_language: string;
          is_synthetic: number;
        }
      | undefined;

    if (!user || user.password_hash !== hashPassword(password)) {
      res.status(401).json({ error: 'Invalid email or password' });
      return;
    }

    const stores = db
      .prepare('SELECT id, store_code, name, city, state, pincode, is_verified FROM stores WHERE owner_id = ? ORDER BY store_code')
      .all(user.id);

    const token = signToken({ sub: user.id, email: user.email, role: user.role });
    res.json({
      access_token: token,
      user: {
        id: user.id,
        email: user.email,
        full_name: user.full_name,
        phone: user.phone,
        role: user.role,
        preferred_language: user.preferred_language,
        is_synthetic: Boolean(user.is_synthetic),
      },
      stores,
    });
  });

  // Auth: Register Store Owner + Store
  const registerSchema = z.object({
    full_name: z.string().min(2).max(120),
    email: z.string().email(),
    password: z.string().min(8),
    phone: z.string().min(8).max(20).optional(),
    store_name: z.string().min(2).max(150),
    city: z.string().min(2).max(80),
    state: z.string().min(2).max(80),
    pincode: z.string().min(6).max(10),
    address: z.string().min(4).max(250),
  });

  app.post('/api/v1/auth/register', (req: Request, res: Response) => {
    const parsed = registerSchema.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: 'Validation failed', details: parsed.error.flatten() });
      return;
    }
    const data = parsed.data;
    const existing = db.prepare('SELECT id FROM users WHERE email = ?').get(data.email.toLowerCase());
    if (existing) {
      res.status(409).json({ error: 'An account with this email already exists' });
      return;
    }

    const nowUtc = new Date().toISOString();
    const userId = crypto.randomUUID();
    const storeId = crypto.randomUUID();
    const countRow = db.prepare('SELECT COUNT(*) AS cnt FROM stores').get() as { cnt: number };
    const storeCode = `KRN-${String(countRow.cnt + 1).padStart(3, '0')}`;

    db.exec('BEGIN TRANSACTION');
    try {
      db.prepare(
        `INSERT INTO users (id, email, password_hash, full_name, phone, role, preferred_language, is_active, is_synthetic, created_at_utc, updated_at_utc)
         VALUES (?, ?, ?, ?, ?, 'owner', 'en', 1, 0, ?, ?)`,
      ).run(userId, data.email.toLowerCase(), hashPassword(data.password), data.full_name, data.phone || null, nowUtc, nowUtc);

      db.prepare(
        `INSERT INTO stores (id, owner_id, store_code, name, address, city, state, pincode, latitude, longitude, is_verified, default_min_margin_bps, clearance_below_margin_allowed, is_synthetic, created_at_utc, updated_at_utc)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, 12.9716, 77.5946, 0, 1000, 0, 0, ?, ?)`,
      ).run(storeId, userId, storeCode, data.store_name, data.address, data.city, data.state, data.pincode, nowUtc, nowUtc);

      db.exec('COMMIT');
    } catch (err) {
      db.exec('ROLLBACK');
      res.status(500).json({ error: 'Failed to create owner and store', detail: String(err) });
      return;
    }

    const token = signToken({ sub: userId, email: data.email.toLowerCase(), role: 'owner' });
    res.status(201).json({
      access_token: token,
      user: {
        id: userId,
        email: data.email.toLowerCase(),
        full_name: data.full_name,
        role: 'owner',
        preferred_language: 'en',
        is_synthetic: false,
      },
      stores: [
        {
          id: storeId,
          store_code: storeCode,
          name: data.store_name,
          city: data.city,
          state: data.state,
          pincode: data.pincode,
          is_verified: 0,
        },
      ],
    });
  });

  // Stores list
  app.get('/api/v1/stores', (_req: Request, res: Response) => {
    const stores = db
      .prepare(
        `SELECT s.*, u.full_name AS owner_name, u.email AS owner_email
         FROM stores s JOIN users u ON s.owner_id = u.id
         ORDER BY s.store_code`,
      )
      .all();
    res.json({ stores });
  });

  // Update store settings
  const storeSettingsSchema = z.object({
    default_min_margin_bps: z.number().int().min(0).max(5000).optional(),
    clearance_below_margin_allowed: z.boolean().optional(),
    preferred_language: z.enum(['en', 'hi', 'kn']).optional(),
  });

  app.patch('/api/v1/stores/:storeId/settings', (req: Request, res: Response) => {
    const parsed = storeSettingsSchema.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: 'Invalid settings payload', details: parsed.error.flatten() });
      return;
    }
    const { storeId } = req.params;
    const store = db.prepare('SELECT id, owner_id FROM stores WHERE id = ?').get(storeId) as
      | { id: string; owner_id: string }
      | undefined;
    if (!store) {
      res.status(404).json({ error: 'Store not found' });
      return;
    }

    const nowUtc = new Date().toISOString();
    if (parsed.data.default_min_margin_bps !== undefined) {
      db.prepare('UPDATE stores SET default_min_margin_bps = ?, updated_at_utc = ? WHERE id = ?').run(
        parsed.data.default_min_margin_bps,
        nowUtc,
        storeId,
      );
    }
    if (parsed.data.clearance_below_margin_allowed !== undefined) {
      db.prepare('UPDATE stores SET clearance_below_margin_allowed = ?, updated_at_utc = ? WHERE id = ?').run(
        parsed.data.clearance_below_margin_allowed ? 1 : 0,
        nowUtc,
        storeId,
      );
    }
    if (parsed.data.preferred_language !== undefined) {
      db.prepare('UPDATE users SET preferred_language = ?, updated_at_utc = ? WHERE id = ?').run(
        parsed.data.preferred_language,
        nowUtc,
        store.owner_id,
      );
    }

    const updated = db.prepare('SELECT * FROM stores WHERE id = ?').get(storeId);
    res.json({ store: updated });
  });

  // Store Dashboard KPIs & Real Aggregations
  app.get('/api/v1/stores/:storeId/dashboard', (req: Request, res: Response) => {
    const { storeId } = req.params;
    const store = db.prepare('SELECT * FROM stores WHERE id = ?').get(storeId) as Record<string, unknown> | undefined;
    if (!store) {
      res.status(404).json({ error: 'Store not found' });
      return;
    }

    const kpis = db
      .prepare(
        `SELECT
           COUNT(*) AS total_products,
           COALESCE(SUM(available_qty), 0) AS total_available_units,
           COALESCE(SUM(CASE WHEN available_qty > 0 AND available_qty <= reorder_point_qty THEN 1 ELSE 0 END), 0) AS low_stock_products,
           COALESCE(SUM(CASE WHEN available_qty = 0 THEN 1 ELSE 0 END), 0) AS out_of_stock_products,
           COALESCE(SUM(CASE WHEN (available_qty + incoming_qty) < reorder_point_qty THEN 1 ELSE 0 END), 0) AS reorder_required_products,
           COALESCE(SUM(CAST(ROUND(available_qty * selling_price_paise) AS INTEGER)), 0) AS stock_retail_value_paise,
           COALESCE(SUM(CAST(ROUND(available_qty * cost_price_paise) AS INTEGER)), 0) AS stock_cost_value_paise
         FROM store_inventory
         WHERE store_id = ?`,
      )
      .get(storeId) as Record<string, number>;

    const expiringCount = db
      .prepare(
        `SELECT COUNT(*) AS expiring_products
         FROM stock_batches
         WHERE store_id = ? AND remaining_qty > 0 AND status = 'expiring_soon'`,
      )
      .get(storeId) as { expiring_products: number };

    const recentUpdates = db
      .prepare(
        `SELECT si.id, p.sku_code, p.name, p.brand, p.category, si.available_qty, si.unit_type,
                si.selling_price_paise, si.mrp_paise, si.version, si.updated_at_utc
         FROM store_inventory si
         JOIN products p ON si.product_id = p.id
         WHERE si.store_id = ?
         ORDER BY si.updated_at_utc DESC, p.sku_code ASC
         LIMIT 8`,
      )
      .all(storeId);

    const salesSeries = db
      .prepare(
        `SELECT substr(sold_at_utc, 1, 10) AS day,
                ROUND(SUM(quantity), 2) AS total_units,
                SUM(total_revenue_paise) AS revenue_paise,
                MAX(festival_tag) AS festival_tag
         FROM sales
         WHERE store_id = ?
         GROUP BY substr(sold_at_utc, 1, 10)
         ORDER BY day DESC
         LIMIT 30`,
      )
      .all(storeId)
      .reverse();

    const categoryBreakdown = db
      .prepare(
        `SELECT p.category,
                COUNT(*) AS sku_count,
                ROUND(SUM(si.available_qty), 2) AS total_qty,
                SUM(CAST(ROUND(si.available_qty * si.selling_price_paise) AS INTEGER)) AS retail_value_paise
         FROM store_inventory si
         JOIN products p ON si.product_id = p.id
         WHERE si.store_id = ?
         GROUP BY p.category
         ORDER BY retail_value_paise DESC`,
      )
      .all(storeId);

    res.json({
      store,
      kpis: {
        ...kpis,
        expiring_products: expiringCount.expiring_products,
      },
      recent_updates: recentUpdates,
      sales_series_30d: salesSeries,
      category_breakdown: categoryBreakdown,
    });
  });

  // Master Product Catalogue (800+ SKUs)
  app.get('/api/v1/products', (req: Request, res: Response) => {
    const search = String(req.query.search || '').trim();
    const category = String(req.query.category || '').trim();
    const looseOnly = req.query.loose_only === 'true';
    const limit = Math.min(200, Math.max(1, Number(req.query.limit || 40)));
    const offset = Math.max(0, Number(req.query.offset || 0));

    const clauses: string[] = [];
    const params: (string | number)[] = [];

    if (search) {
      clauses.push('(p.name LIKE ? OR p.brand LIKE ? OR p.sku_code LIKE ?)');
      const pat = `%${search}%`;
      params.push(pat, pat, pat);
    }
    if (category) {
      clauses.push('p.category = ?');
      params.push(category);
    }
    if (looseOnly) {
      clauses.push('p.is_loose_commodity = 1');
    }

    const whereSql = clauses.length > 0 ? `WHERE ${clauses.join(' AND ')}` : '';
    const totalRow = db.prepare(`SELECT COUNT(*) AS cnt FROM products p ${whereSql}`).get(...params) as {
      cnt: number;
    };
    const items = db
      .prepare(
        `SELECT p.*, pi.image_url AS reference_image_url
         FROM products p
         LEFT JOIN product_images pi ON pi.product_id = p.id AND pi.is_reference = 1
         ${whereSql}
         GROUP BY p.id
         ORDER BY p.sku_code ASC
         LIMIT ? OFFSET ?`,
      )
      .all(...params, limit, offset);

    const categories = db
      .prepare('SELECT category, COUNT(*) AS count FROM products GROUP BY category ORDER BY category')
      .all();

    res.json({
      total: totalRow.cnt,
      limit,
      offset,
      categories,
      items,
    });
  });

  const createProductSchema = z
    .object({
      name: z.string().min(2).max(200),
      brand: z.string().min(1).max(100),
      variant: z.string().max(100).default('Standard'),
      category: z.string().min(2).max(80),
      unit_type: z.enum(['pcs', 'kg', 'g', 'l', 'ml', 'pack']),
      pack_size_value: z.number().positive(),
      pack_size_unit: z.string().min(1).max(16),
      is_loose_commodity: z.boolean().default(false),
      mrp_paise: z.number().int().positive(),
      default_cost_paise: z.number().int().nonnegative(),
      expiry_category: z.enum(['dairy', 'bakery', 'snacks', 'grocery', 'other']).default('grocery'),
    })
    .refine((d) => d.default_cost_paise <= d.mrp_paise, {
      message: 'Cost price cannot exceed MRP',
      path: ['default_cost_paise'],
    });

  app.post('/api/v1/products', (req: Request, res: Response) => {
    const parsed = createProductSchema.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: 'Invalid product payload', details: parsed.error.flatten() });
      return;
    }
    const d = parsed.data;
    const nowUtc = new Date().toISOString();
    const id = crypto.randomUUID();
    const cntRow = db.prepare('SELECT COUNT(*) AS cnt FROM products').get() as { cnt: number };
    const skuCode = `SKU-${String(cntRow.cnt + 1).padStart(4, '0')}`;

    db.prepare(
      `INSERT INTO products (id, sku_code, barcode, name, brand, variant, category, subcategory, unit_type, pack_size_value, pack_size_unit, is_loose_commodity, mrp_paise, default_cost_paise, gst_bps, expiry_category, is_synthetic, created_at_utc, updated_at_utc)
       VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 500, ?, 0, ?, ?)`,
    ).run(
      id,
      skuCode,
      d.name,
      d.brand,
      d.variant,
      d.category,
      d.category,
      d.unit_type,
      d.pack_size_value,
      d.pack_size_unit,
      d.is_loose_commodity ? 1 : 0,
      d.mrp_paise,
      d.default_cost_paise,
      d.expiry_category,
      nowUtc,
      nowUtc,
    );

    const created = db.prepare('SELECT * FROM products WHERE id = ?').get(id);
    res.status(201).json({ product: created });
  });

  // Store Inventory List
  app.get('/api/v1/stores/:storeId/inventory', (req: Request, res: Response) => {
    const { storeId } = req.params;
    const search = String(req.query.search || '').trim();
    const statusFilter = String(req.query.filter || 'all');

    const clauses = ['si.store_id = ?'];
    const params: (string | number)[] = [storeId];

    if (search) {
      clauses.push('(p.name LIKE ? OR p.brand LIKE ? OR p.sku_code LIKE ?)');
      const pat = `%${search}%`;
      params.push(pat, pat, pat);
    }
    if (statusFilter === 'low_stock') {
      clauses.push('si.available_qty > 0 AND si.available_qty <= si.reorder_point_qty');
    } else if (statusFilter === 'out_of_stock') {
      clauses.push('si.available_qty = 0');
    } else if (statusFilter === 'loose') {
      clauses.push('p.is_loose_commodity = 1');
    } else if (statusFilter === 'expiring_soon') {
      clauses.push("EXISTS (SELECT 1 FROM stock_batches sb WHERE sb.store_inventory_id = si.id AND sb.status = 'expiring_soon' AND sb.remaining_qty > 0)");
    }

    const rows = db
      .prepare(
        `SELECT si.*, p.sku_code, p.name, p.brand, p.category, p.expiry_category, p.is_loose_commodity,
                sup.name AS supplier_name, sup.lead_time_days,
                (SELECT MIN(sb.expiry_date) FROM stock_batches sb WHERE sb.store_inventory_id = si.id AND sb.remaining_qty > 0) AS nearest_expiry_date
         FROM store_inventory si
         JOIN products p ON si.product_id = p.id
         LEFT JOIN suppliers sup ON si.supplier_id = sup.id
         WHERE ${clauses.join(' AND ')}
         ORDER BY p.sku_code ASC`,
      )
      .all(...params);

    res.json({ items: rows });
  });

  // Update Store Inventory (enforces selling_price <= MRP, reserved <= available, and optimistic locking)
  const updateInvSchema = z.object({
    available_qty: z.number().nonnegative().optional(),
    reserved_qty: z.number().nonnegative().optional(),
    selling_price_paise: z.number().int().positive().optional(),
    clearance_enabled: z.boolean().optional(),
    version: z.number().int().positive(),
  });

  app.patch('/api/v1/stores/:storeId/inventory/:inventoryId', (req: Request, res: Response) => {
    const parsed = updateInvSchema.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: 'Invalid inventory update', details: parsed.error.flatten() });
      return;
    }
    const { storeId, inventoryId } = req.params;
    const current = db
      .prepare('SELECT * FROM store_inventory WHERE id = ? AND store_id = ?')
      .get(inventoryId, storeId) as
      | {
          id: string;
          store_id: string;
          product_id: string;
          available_qty: number;
          reserved_qty: number;
          selling_price_paise: number;
          mrp_paise: number;
          clearance_enabled: number;
          version: number;
        }
      | undefined;

    if (!current) {
      res.status(404).json({ error: 'Inventory record not found' });
      return;
    }
    if (current.version !== parsed.data.version) {
      res.status(409).json({
        error: 'Optimistic locking conflict: inventory record was modified elsewhere',
        current_version: current.version,
      });
      return;
    }

    const nextAvail = parsed.data.available_qty ?? current.available_qty;
    const nextRes = parsed.data.reserved_qty ?? current.reserved_qty;
    const nextPrice = parsed.data.selling_price_paise ?? current.selling_price_paise;
    const nextClearance =
      parsed.data.clearance_enabled !== undefined
        ? parsed.data.clearance_enabled
          ? 1
          : 0
        : current.clearance_enabled;

    if (nextRes > nextAvail) {
      res.status(422).json({ error: 'Constraint violation: reserved_qty cannot exceed available_qty' });
      return;
    }
    if (nextPrice > current.mrp_paise) {
      res.status(422).json({ error: 'Constraint violation: selling_price_paise cannot exceed mrp_paise' });
      return;
    }

    const nowUtc = new Date().toISOString();
    db.exec('BEGIN TRANSACTION');
    try {
      db.prepare(
        `UPDATE store_inventory
         SET available_qty = ?, reserved_qty = ?, selling_price_paise = ?, clearance_enabled = ?,
             version = version + 1, updated_at_utc = ?,
             last_price_changed_at_utc = CASE WHEN ? != ? THEN ? ELSE last_price_changed_at_utc END
         WHERE id = ? AND version = ?`,
      ).run(
        nextAvail,
        nextRes,
        nextPrice,
        nextClearance,
        nowUtc,
        nextPrice,
        current.selling_price_paise,
        nowUtc,
        inventoryId,
        current.version,
      );

      if (nextPrice !== current.selling_price_paise) {
        db.prepare(
          `INSERT INTO price_history (id, store_id, product_id, old_price_paise, new_price_paise, mrp_paise, change_source, pricing_recommendation_id, changed_by_user_id, changed_at_utc)
           VALUES (?, ?, ?, ?, ?, ?, 'owner_manual', NULL, NULL, ?)`,
        ).run(
          crypto.randomUUID(),
          storeId,
          current.product_id,
          current.selling_price_paise,
          nextPrice,
          current.mrp_paise,
          nowUtc,
        );
      }

      db.exec('COMMIT');
    } catch (err) {
      db.exec('ROLLBACK');
      res.status(500).json({ error: 'Failed to update inventory', detail: String(err) });
      return;
    }

    const updated = db.prepare('SELECT * FROM store_inventory WHERE id = ?').get(inventoryId);
    res.json({ item: updated });
  });

  // Stock Batches
  app.get('/api/v1/stores/:storeId/batches', (req: Request, res: Response) => {
    const { storeId } = req.params;
    const rows = db
      .prepare(
        `SELECT sb.*, p.sku_code, p.name, p.brand, p.category, p.expiry_category
         FROM stock_batches sb
         JOIN products p ON sb.product_id = p.id
         WHERE sb.store_id = ?
         ORDER BY sb.expiry_date ASC`,
      )
      .all(storeId);
    res.json({ batches: rows });
  });

  // Nearby Verified Competitor Comparison (within 2 km radius)
  app.get('/api/v1/stores/:storeId/competitor-comparison', (req: Request, res: Response) => {
    const { storeId } = req.params;
    const store = db.prepare('SELECT id, latitude, longitude, name FROM stores WHERE id = ?').get(storeId) as
      | { id: string; latitude: number; longitude: number; name: string }
      | undefined;
    if (!store) {
      res.status(404).json({ error: 'Store not found' });
      return;
    }

    const otherStores = db
      .prepare('SELECT id, name, latitude, longitude, is_verified FROM stores WHERE id != ? AND is_verified = 1')
      .all(storeId) as Array<{ id: string; name: string; latitude: number; longitude: number; is_verified: number }>;

    const nearbyIds = otherStores
      .map((s) => ({ ...s, distance_km: haversineKm(store.latitude, store.longitude, s.latitude, s.longitude) }))
      .filter((s) => s.distance_km <= 2.0);

    const storeInv = db
      .prepare(
        `SELECT si.product_id, si.selling_price_paise, si.mrp_paise, si.cost_price_paise,
                p.sku_code, p.name, p.category
         FROM store_inventory si
         JOIN products p ON si.product_id = p.id
         WHERE si.store_id = ?
         LIMIT 45`,
      )
      .all(storeId) as Array<{
      product_id: string;
      selling_price_paise: number;
      mrp_paise: number;
      cost_price_paise: number;
      sku_code: string;
      name: string;
      category: string;
    }>;

    const comparisons = storeInv.map((item) => {
      let peerPrices: number[] = [];
      if (nearbyIds.length > 0) {
        const placeholders = nearbyIds.map(() => '?').join(',');
        const rows = db
          .prepare(
            `SELECT selling_price_paise FROM store_inventory WHERE product_id = ? AND store_id IN (${placeholders})`,
          )
          .all(item.product_id, ...nearbyIds.map((n) => n.id)) as Array<{ selling_price_paise: number }>;
        peerPrices = rows.map((r) => r.selling_price_paise).sort((a, b) => a - b);
      }
      const median =
        peerPrices.length > 0
          ? peerPrices[Math.floor(peerPrices.length / 2)]
          : null;
      const diffPct =
        median && median > 0
          ? Math.round(((item.selling_price_paise - median) / median) * 1000) / 10
          : null;
      return {
        ...item,
        nearby_verified_stores: peerPrices.length,
        nearby_median_paise: median,
        diff_vs_median_pct: diffPct,
      };
    });

    res.json({
      store_id: storeId,
      radius_km: 2.0,
      nearby_verified_store_count: nearbyIds.length,
      nearby_stores: nearbyIds,
      comparisons,
    });
  });

  // 180-Day Sales History Preview (Stage 1 foundation for Stage 4 Forecasting)
  app.get('/api/v1/stores/:storeId/sales-history', (req: Request, res: Response) => {
    const { storeId } = req.params;
    const daily = db
      .prepare(
        `SELECT substr(sold_at_utc, 1, 10) AS date,
                ROUND(SUM(quantity), 2) AS units_sold,
                SUM(total_revenue_paise) AS revenue_paise,
                MAX(festival_tag) AS festival_tag
         FROM sales
         WHERE store_id = ?
         GROUP BY substr(sold_at_utc, 1, 10)
         ORDER BY date ASC`,
      )
      .all(storeId);
    res.json({ store_id: storeId, days: daily.length, series: daily });
  });

  // Agent Runs History
  app.get('/api/v1/stores/:storeId/agent-runs', (req: Request, res: Response) => {
    const { storeId } = req.params;
    const runs = db
      .prepare('SELECT * FROM agent_runs WHERE store_id = ? OR store_id IS NULL ORDER BY started_at_utc DESC LIMIT 50')
      .all(storeId);
    res.json({ runs });
  });

  // Server-Side Gemini API Explanation Endpoint (with deterministic fallback)
  app.post('/api/v1/ai/explain-summary', async (req: Request, res: Response) => {
    const storeId = String(req.body?.store_id || '');
    if (!storeId) {
      res.status(400).json({ error: 'store_id is required' });
      return;
    }

    const store = db.prepare('SELECT name, city FROM stores WHERE id = ?').get(storeId) as
      | { name: string; city: string }
      | undefined;
    if (!store) {
      res.status(404).json({ error: 'Store not found' });
      return;
    }

    const stats = db
      .prepare(
        `SELECT
           COUNT(*) AS total_skus,
           COALESCE(SUM(CASE WHEN available_qty = 0 THEN 1 ELSE 0 END), 0) AS out_of_stock,
           COALESCE(SUM(CASE WHEN available_qty > 0 AND available_qty <= reorder_point_qty THEN 1 ELSE 0 END), 0) AS low_stock
         FROM store_inventory WHERE store_id = ?`,
      )
      .get(storeId) as { total_skus: number; out_of_stock: number; low_stock: number };

    const expiring = db
      .prepare(
        `SELECT COUNT(*) AS cnt FROM stock_batches WHERE store_id = ? AND remaining_qty > 0 AND status = 'expiring_soon'`,
      )
      .get(storeId) as { cnt: number };

    const deterministicFallback = `${store.name} (${store.city}) tracks ${stats.total_skus} active SKUs in the Stage 1 foundation database: ${stats.low_stock} SKUs are at or below reorder threshold, ${stats.out_of_stock} SKUs are out of stock, and ${expiring.cnt} stock batches expire within 7 days. All numerical metrics are computed deterministically from store_inventory and stock_batches.`;

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey || apiKey === 'MY_GEMINI_API_KEY') {
      res.json({
        summary: deterministicFallback,
        provider: 'deterministic-fallback',
        fallback_used: true,
      });
      return;
    }

    try {
      const ai = new GoogleGenAI({
        apiKey,
        httpOptions: { headers: { 'User-Agent': 'aistudio-build' } },
      });
      const response = await ai.models.generateContent({
        model: 'gemini-4-hydrogen',
        contents: `Summarize this Kirana store's Stage 1 inventory posture in 2 crisp, factual sentences without inventing any numbers:\nStore: ${store.name}, ${store.city}\nActive SKUs: ${stats.total_skus}\nLow Stock SKUs: ${stats.low_stock}\nOut of Stock SKUs: ${stats.out_of_stock}\nExpiring Batches (<=7d): ${expiring.cnt}`,
      });
      res.json({
        summary: response.text?.trim() || deterministicFallback,
        provider: 'gemini-4-hydrogen',
        fallback_used: false,
      });
    } catch {
      res.json({
        summary: deterministicFallback,
        provider: 'deterministic-fallback',
        fallback_used: true,
      });
    }
  });

  return app;
}

async function startServer() {
  const app = createApp();

  if (process.env.NODE_ENV === 'production') {
    const distDir = path.resolve('dist');
    app.use(express.static(distDir));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distDir, 'index.html'));
    });
  } else {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`AI Powered Retail Connect (Stage 1) running on http://0.0.0.0:${PORT}`);
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  startServer();
}
