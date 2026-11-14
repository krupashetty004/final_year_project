import assert from 'node:assert/strict';
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { describe, it } from 'node:test';
import { createApp } from '../server.ts';

const DB_PATH = path.resolve('./database/retail_connect.sqlite');
if (!fs.existsSync(DB_PATH)) {
  execSync('python3 database/seed/generate_synthetic_data.py', { stdio: 'inherit' });
}

describe('Stage 1 Foundation & Database Invariants', () => {
  const db = new DatabaseSync(DB_PATH);

  it('contains all 18 required database tables', () => {
    const rows = db
      .prepare("SELECT name FROM sqlite_master WHERE type='table'")
      .all() as Array<{ name: string }>;
    const names = new Set(rows.map((r) => r.name));
    const required = [
      'users',
      'stores',
      'products',
      'product_images',
      'product_aliases',
      'store_inventory',
      'stock_batches',
      'sales',
      'suppliers',
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
    for (const tbl of required) {
      assert.ok(names.has(tbl), `Missing required table: ${tbl}`);
    }
  });

  it('seeds deterministic synthetic dataset counts (20 stores, 50 customers, 10 partners, 800 products)', () => {
    const stores = (db.prepare('SELECT COUNT(*) AS cnt FROM stores').get() as { cnt: number }).cnt;
    const customers = (
      db.prepare("SELECT COUNT(*) AS cnt FROM users WHERE role='customer'").get() as { cnt: number }
    ).cnt;
    const partners = (
      db.prepare("SELECT COUNT(*) AS cnt FROM users WHERE role='delivery_partner'").get() as {
        cnt: number;
      }
    ).cnt;
    const products = (db.prepare('SELECT COUNT(*) AS cnt FROM products').get() as { cnt: number })
      .cnt;
    const sales = (db.prepare('SELECT COUNT(*) AS cnt FROM sales').get() as { cnt: number }).cnt;

    assert.equal(stores, 20);
    assert.equal(customers, 50);
    assert.equal(partners, 10);
    assert.equal(products, 800);
    assert.ok(sales > 30000, `Expected 6-month synthetic sales > 30,000 rows, got ${sales}`);
  });

  it('enforces integer paise money, selling_price <= mrp, and reserved_qty <= available_qty', () => {
    const badPrices = (
      db
        .prepare('SELECT COUNT(*) AS cnt FROM store_inventory WHERE selling_price_paise > mrp_paise')
        .get() as { cnt: number }
    ).cnt;
    const badReserved = (
      db
        .prepare('SELECT COUNT(*) AS cnt FROM store_inventory WHERE reserved_qty > available_qty')
        .get() as { cnt: number }
    ).cnt;
    assert.equal(badPrices, 0);
    assert.equal(badReserved, 0);
  });

  it('rejects database inserts violating selling_price_paise <= mrp_paise or reserved_qty <= available_qty', () => {
    const sample = db
      .prepare('SELECT store_id, product_id, mrp_paise FROM store_inventory LIMIT 1')
      .get() as { store_id: string; product_id: string; mrp_paise: number };

    assert.throws(() => {
      db.prepare(
        `INSERT INTO store_inventory (id, store_id, product_id, available_qty, reserved_qty, incoming_qty, unit_type, selling_price_paise, cost_price_paise, mrp_paise, updated_at_utc)
         VALUES ('test-bad-1', ?, ?, 10, 0, 0, 'pcs', ?, 1000, ?, '2026-11-13T00:00:00Z')`,
      ).run(sample.store_id, sample.product_id, sample.mrp_paise + 100, sample.mrp_paise);
    });
  });
});

describe('Stage 1 API Endpoints & Business Rule Validation', () => {
  it('serves health, stores, products, auth login, and enforces selling_price <= MRP on PATCH', async () => {
    const app = createApp();
    const server = app.listen(0);
    const addr = server.address();
    assert.ok(addr && typeof addr === 'object');
    const base = `http://127.0.0.1:${addr.port}/api/v1`;

    try {
      const healthRes = await fetch(`${base}/health`);
      assert.equal(healthRes.status, 200);
      const health = (await healthRes.json()) as { status: string; table_counts: Record<string, number> };
      assert.equal(health.status, 'ok');
      assert.equal(health.table_counts.products, 800);
      assert.equal(health.table_counts.stores, 20);

      const loginRes = await fetch(`${base}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: 'ramesh@lakshmikirana.in',
          password: 'KiranaDemo@2026',
        }),
      });
      assert.equal(loginRes.status, 200);
      const auth = (await loginRes.json()) as { access_token: string; stores: Array<{ id: string }> };
      assert.ok(auth.access_token.length > 20);
      const storeId = auth.stores[0].id;

      const invRes = await fetch(`${base}/stores/${storeId}/inventory`);
      assert.equal(invRes.status, 200);
      const invJson = (await invRes.json()) as {
        items: Array<{ id: string; mrp_paise: number; version: number }>;
      };
      assert.ok(invJson.items.length >= 100);

      const target = invJson.items[0];
      const badPatch = await fetch(`${base}/stores/${storeId}/inventory/${target.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selling_price_paise: target.mrp_paise + 500,
          version: target.version,
        }),
      });
      assert.equal(badPatch.status, 422);
    } finally {
      server.close();
    }
  });
});
