"""
Deterministic Synthetic Dataset Generator (Stage 1 - AI Powered Retail Connect).

Uses a fixed random seed (SEED = 42) to generate reproducible synthetic data:
- 20 simulated Kirana stores (plus 20 store owners)
- 50 simulated customers
- 10 simulated delivery partners
- 800 common Indian grocery products across 9 required categories
- Suppliers with lead times
- Store inventory records with unique (store_id, product_id)
- Stock batches with realistic expiry dates
- 6 months (180 days) of synthetic sales history with Indian festival indicators
- Competitor price observations from verified nearby stores within 2 km

All generated records are marked `is_synthetic = 1` / `TRUE`.
All monetary values are stored in integer paise.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SEED = int(os.getenv("SYNTHETIC_SEED", "42"))
NAMESPACE_UUID = uuid.UUID("a1b2c3d4-e5f6-4789-abcd-100000000042")

CATEGORIES = [
    ("Rice and grains", "grocery", ["Sona Masoori Rice", "Basmati Rice", "Kolam Rice", "Ragi Flour", "Chakki Atta", "Jowar Flour", "Poha", "Suji Rava", "Maida", "Dalia"]),
    ("Pulses and dals", "grocery", ["Toor Dal", "Moong Dal", "Chana Dal", "Urad Dal", "Masoor Dal", "Kabuli Chana", "Rajma Chitra", "Green Moong", "Kala Chana", "Roasted Gram"]),
    ("Cooking oils", "grocery", ["Refined Sunflower Oil", "Cold Pressed Groundnut Oil", "Mustard Oil", "Filtered Gingelly Oil", "Rice Bran Oil", "Coconut Cooking Oil", "Desi Cow Ghee", "Vanaspati", "Blended Vegetable Oil", "Olive Pomace Oil"]),
    ("Dairy", "dairy", ["Toned Fresh Milk", "Full Cream Milk", "Thick Curd Pouch", "Salted Butter", "Fresh Paneer", "Cheese Slices", "Lassi Mango", "Buttermilk Spiced", "UHT Milk", "Khoya Fresh"]),
    ("Snacks", "snacks", ["Salted Potato Chips", "Masala Peanuts", "Aloo Bhujia", "Khatta Meetha Mix", "Marie Gold Biscuits", "Butter Cookies", "Cream Cracker", "Salted Makhana", "Rusk Toast", "Khakhra Methi"]),
    ("Beverages", "other", ["Assam Leaf Tea", "Filter Coffee Powder", "Instant Coffee", "Mango Juice Tetra", "Masala Chai Premix", "Lemonade Spark", "Glucose Energy Drink", "Malted Health Drink", "Tender Coconut Water", "Badam Milk"]),
    ("Personal care", "other", ["Neem Herbal Soap", "Coconut Hair Oil", "Herbal Toothpaste", "Anti-Dandruff Shampoo", "Talcum Powder", "Aloe Handwash", "Moisturizing Cream", "Shaving Foam", "Sanitary Pads", "Lip Balm"]),
    ("Household essentials", "other", ["Detergent Washing Powder", "Dishwash Liquid Gel", "Floor Disinfectant", "Toilet Cleaner", "Garbage Bags Roll", "Agarbatti Incense", "Scrubber Pad", "Mosquito Vaporizer", "Aluminium Foil", "Camphor Tablets"]),
    ("Packaged foods", "grocery", ["Instant Noodles Masala", "Tomato Ketchup", "Whole Wheat Bread", "Idli Dosa Batter", "Mixed Fruit Jam", "Sambar Masala", "Garam Masala", "Red Chilli Powder", "Turmeric Powder", "Poha Ready Mix"]),
]

BRANDS_BY_CATEGORY = {
    "Rice and grains": ["India Gate", "Daawat", "Aashirvaad", "Fortune", "24 Mantra", "Kirana Loose", "Royal", "Pillsbury"],
    "Pulses and dals": ["Tata Sampann", "24 Mantra", "Kirana Loose", "Fortune", "BB Popular", "Organic Tattva", "Pro Nature"],
    "Cooking oils": ["Fortune", "Saffola", "Sunpure", "Gold Winner", "Dhara", "Amul", "Nandini", "Idhayam"],
    "Dairy": ["Amul", "Nandini", "Mother Dairy", "Milky Mist", "Britannia", "Dodla", "Hatsun"],
    "Snacks": ["Lay's", "Haldiram's", "Britannia", "Parle", "Bikaji", "Balaji", "Sunfeast", "Modern Bakery"],
    "Beverages": ["Tata Tea", "Red Label", "Bru", "Nescafe", "Maaza", "Paper Boat", "Horlicks", "Real"],
    "Personal care": ["Himalaya", "Parachute", "Dabur", "Colgate", "Dettol", "Santoor", "Clinic Plus", "Nivea"],
    "Household essentials": ["Surf Excel", "Vim", "Lizol", "Harpic", "Ariel", "Mangaldeep", "Scotch-Brite", "Good Knight"],
    "Packaged foods": ["Maggi", "Kissan", "MTR", "Modern", "ID Fresh", "Everest", "MDH", "Aachi"],
}

VARIANTS_AND_PACKS = [
    ("Classic", 1.0, "kg", "kg", True),
    ("Premium", 500.0, "g", "pcs", False),
    ("Family Pack", 1.0, "kg", "pcs", False),
    ("Value Pouch", 200.0, "g", "pcs", False),
    ("Regular", 250.0, "g", "pcs", False),
    ("Economy", 2.0, "kg", "pcs", False),
    ("Standard", 500.0, "ml", "pcs", False),
    ("Jumbo", 1.0, "l", "pcs", False),
    ("Mini", 100.0, "g", "pcs", False),
    ("Fresh Pack", 400.0, "g", "pcs", False),
]

STORE_CITIES = [
    ("Bengaluru", "Karnataka", "560038", 12.9784, 77.6408),
    ("Bengaluru", "Karnataka", "560034", 12.9352, 77.6245),
    ("Bengaluru", "Karnataka", "560011", 12.9279, 77.5838),
    ("Bengaluru", "Karnataka", "560078", 12.9063, 77.5857),
    ("Mysuru", "Karnataka", "570001", 12.3052, 76.6552),
    ("Pune", "Maharashtra", "411004", 18.5196, 73.8415),
    ("Hyderabad", "Telangana", "500034", 17.4126, 78.4480),
    ("Chennai", "Tamil Nadu", "600017", 13.0418, 80.2341),
]

STORE_NAMES = [
    "Sri Lakshmi Kirana & Provision",
    "Annapurna Super Mart",
    "Kaveri Daily Needs",
    "Nandi Provision Stores",
    "Ganesh Hyperlocal Kirana",
    "Balaji Grain & Oil Emporium",
    "Shree Sai Kirana Kendra",
    "Vijaya Lakshmi General Store",
    "Metro Fresh Kirana",
    "Deccan Neighbourhood Mart",
    "Chamundi Provision Store",
    "Surya Kirana & Dairy",
    "Bharathi Family Provisions",
    "Cauvery Traders & Kirana",
    "Padmavathi Daily Mart",
    "Omkar Kirana Bazar",
    "Sahyadri Provision House",
    "Narmada Super Kirana",
    "Maruthi Fresh & Staples",
    "Kasturi Kirana Corner",
]

INDIAN_FESTIVALS = [
    ("Ugadi", 155),
    ("Ganesh Chaturthi", 95),
    ("Dasara", 48),
    ("Deepavali", 18),
    ("Sankranti", 125),
]


def det_uuid(key: str) -> str:
    return str(uuid.uuid5(NAMESPACE_UUID, key))


def hash_password(raw: str) -> str:
    return hashlib.sha256(f"retail_connect_salt::{raw}".encode("utf-8")).hexdigest()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 3)


SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  full_name TEXT NOT NULL,
  phone TEXT,
  role TEXT NOT NULL CHECK (role IN ('owner', 'staff', 'admin', 'customer', 'delivery_partner')),
  preferred_language TEXT NOT NULL DEFAULT 'en',
  is_active INTEGER NOT NULL DEFAULT 1,
  is_synthetic INTEGER NOT NULL DEFAULT 0,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stores (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id),
  store_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  address TEXT NOT NULL,
  city TEXT NOT NULL,
  state TEXT NOT NULL,
  pincode TEXT NOT NULL,
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  is_verified INTEGER NOT NULL DEFAULT 0,
  default_min_margin_bps INTEGER NOT NULL DEFAULT 1000,
  clearance_below_margin_allowed INTEGER NOT NULL DEFAULT 0,
  is_synthetic INTEGER NOT NULL DEFAULT 0,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY,
  sku_code TEXT NOT NULL UNIQUE,
  barcode TEXT,
  name TEXT NOT NULL,
  brand TEXT NOT NULL,
  variant TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL,
  subcategory TEXT NOT NULL DEFAULT '',
  unit_type TEXT NOT NULL CHECK (unit_type IN ('pcs', 'kg', 'g', 'l', 'ml', 'pack')),
  pack_size_value REAL NOT NULL CHECK (pack_size_value > 0),
  pack_size_unit TEXT NOT NULL,
  is_loose_commodity INTEGER NOT NULL DEFAULT 0,
  mrp_paise INTEGER NOT NULL CHECK (mrp_paise > 0),
  default_cost_paise INTEGER NOT NULL CHECK (default_cost_paise >= 0 AND default_cost_paise <= mrp_paise),
  gst_bps INTEGER NOT NULL DEFAULT 500,
  expiry_category TEXT NOT NULL CHECK (expiry_category IN ('dairy', 'bakery', 'snacks', 'grocery', 'other')),
  is_synthetic INTEGER NOT NULL DEFAULT 0,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product_images (
  id TEXT PRIMARY KEY,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  store_id TEXT REFERENCES stores(id) ON DELETE SET NULL,
  image_url TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  is_reference INTEGER NOT NULL DEFAULT 1,
  embedding_vector TEXT,
  embedding_model TEXT NOT NULL DEFAULT 'dinov2-small',
  ocr_extracted_text TEXT,
  created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product_aliases (
  id TEXT PRIMARY KEY,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  alias_text TEXT NOT NULL,
  language_code TEXT NOT NULL DEFAULT 'en',
  source TEXT NOT NULL DEFAULT 'catalogue',
  created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suppliers (
  id TEXT PRIMARY KEY,
  store_id TEXT REFERENCES stores(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  contact_phone TEXT,
  city TEXT NOT NULL,
  lead_time_days INTEGER NOT NULL CHECK (lead_time_days >= 1),
  min_order_value_paise INTEGER NOT NULL DEFAULT 0,
  reliability_score REAL NOT NULL DEFAULT 0.95,
  is_synthetic INTEGER NOT NULL DEFAULT 0,
  created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS store_inventory (
  id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  available_qty REAL NOT NULL CHECK (available_qty >= 0),
  reserved_qty REAL NOT NULL DEFAULT 0 CHECK (reserved_qty >= 0 AND reserved_qty <= available_qty),
  incoming_qty REAL NOT NULL DEFAULT 0 CHECK (incoming_qty >= 0),
  unit_type TEXT NOT NULL CHECK (unit_type IN ('pcs', 'kg', 'g', 'l', 'ml', 'pack')),
  selling_price_paise INTEGER NOT NULL CHECK (selling_price_paise > 0),
  cost_price_paise INTEGER NOT NULL CHECK (cost_price_paise >= 0),
  mrp_paise INTEGER NOT NULL CHECK (selling_price_paise <= mrp_paise),
  min_margin_bps INTEGER NOT NULL DEFAULT 1000,
  reorder_point_qty REAL NOT NULL DEFAULT 0,
  safety_stock_qty REAL NOT NULL DEFAULT 0,
  supplier_id TEXT REFERENCES suppliers(id),
  supplier_pack_size REAL NOT NULL DEFAULT 1,
  is_listed INTEGER NOT NULL DEFAULT 1,
  clearance_enabled INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  last_price_changed_at_utc TEXT,
  updated_at_utc TEXT NOT NULL,
  UNIQUE(store_id, product_id)
);

CREATE TABLE IF NOT EXISTS stock_batches (
  id TEXT PRIMARY KEY,
  store_inventory_id TEXT NOT NULL REFERENCES store_inventory(id) ON DELETE CASCADE,
  store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  batch_code TEXT NOT NULL,
  initial_qty REAL NOT NULL CHECK (initial_qty >= 0),
  remaining_qty REAL NOT NULL CHECK (remaining_qty >= 0),
  cost_price_paise INTEGER NOT NULL CHECK (cost_price_paise >= 0),
  manufactured_date TEXT,
  expiry_date TEXT,
  clearance_enabled INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
  id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  batch_id TEXT REFERENCES stock_batches(id),
  customer_id TEXT REFERENCES users(id),
  sold_at_utc TEXT NOT NULL,
  quantity REAL NOT NULL CHECK (quantity > 0),
  unit_type TEXT NOT NULL,
  unit_selling_price_paise INTEGER NOT NULL CHECK (unit_selling_price_paise > 0),
  unit_cost_paise INTEGER NOT NULL CHECK (unit_cost_paise >= 0),
  total_revenue_paise INTEGER NOT NULL CHECK (total_revenue_paise >= 0),
  was_promotional INTEGER NOT NULL DEFAULT 0,
  festival_tag TEXT,
  is_synthetic INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id TEXT PRIMARY KEY,
  agent_type TEXT NOT NULL,
  store_id TEXT REFERENCES stores(id) ON DELETE CASCADE,
  model_name TEXT NOT NULL,
  model_version TEXT NOT NULL,
  status TEXT NOT NULL,
  input_payload TEXT NOT NULL DEFAULT '{}',
  output_payload TEXT NOT NULL DEFAULT '{}',
  latency_ms INTEGER NOT NULL DEFAULT 0,
  fallback_used INTEGER NOT NULL DEFAULT 0,
  fallback_reason TEXT,
  started_at_utc TEXT NOT NULL,
  completed_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS demand_forecasts (
  id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  forecast_date TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  model_name TEXT NOT NULL,
  predicted_qty REAL NOT NULL,
  lower_bound_qty REAL NOT NULL,
  upper_bound_qty REAL NOT NULL,
  forecast_error_sigma REAL NOT NULL DEFAULT 0,
  wape_score REAL,
  mae_score REAL,
  rmse_score REAL,
  mase_score REAL,
  agent_run_id TEXT REFERENCES agent_runs(id),
  created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reorder_suggestions (
  id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  supplier_id TEXT REFERENCES suppliers(id),
  current_available_qty REAL NOT NULL,
  incoming_qty REAL NOT NULL,
  expected_lead_time_demand_qty REAL NOT NULL,
  safety_stock_qty REAL NOT NULL,
  reorder_point_qty REAL NOT NULL,
  supplier_pack_size REAL NOT NULL,
  raw_suggested_qty REAL NOT NULL,
  rounded_suggested_qty REAL NOT NULL,
  estimated_cost_paise INTEGER NOT NULL,
  explanation TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  owner_final_qty REAL,
  agent_run_id TEXT REFERENCES agent_runs(id),
  created_at_utc TEXT NOT NULL,
  decided_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS pricing_recommendations (
  id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  batch_id TEXT REFERENCES stock_batches(id),
  current_price_paise INTEGER NOT NULL,
  mrp_paise INTEGER NOT NULL,
  cost_price_paise INTEGER NOT NULL,
  nearby_median_price_paise INTEGER,
  demand_signal_price_paise INTEGER,
  expiry_discount_pct REAL NOT NULL DEFAULT 0,
  competition_signal_price_paise INTEGER,
  stock_pressure_factor REAL NOT NULL DEFAULT 1.0,
  recommended_price_paise INTEGER NOT NULL CHECK (recommended_price_paise > 0 AND recommended_price_paise <= mrp_paise),
  expected_margin_bps INTEGER NOT NULL,
  expected_sell_through_delta_pct REAL NOT NULL DEFAULT 0,
  explanation TEXT NOT NULL,
  constraints_passed INTEGER NOT NULL DEFAULT 1,
  constraint_notes TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  owner_final_price_paise INTEGER,
  agent_run_id TEXT REFERENCES agent_runs(id),
  created_at_utc TEXT NOT NULL,
  decided_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS price_history (
  id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  old_price_paise INTEGER NOT NULL,
  new_price_paise INTEGER NOT NULL,
  mrp_paise INTEGER NOT NULL CHECK (new_price_paise <= mrp_paise),
  change_source TEXT NOT NULL,
  pricing_recommendation_id TEXT REFERENCES pricing_recommendations(id),
  changed_by_user_id TEXT REFERENCES users(id),
  changed_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS competitor_prices (
  id TEXT PRIMARY KEY,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  competitor_store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  observed_at_utc TEXT NOT NULL,
  selling_price_paise INTEGER NOT NULL,
  distance_km REAL NOT NULL,
  is_verified INTEGER NOT NULL DEFAULT 1,
  is_synthetic INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS inventory_image_uploads (
  id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  uploaded_by_user_id TEXT NOT NULL REFERENCES users(id),
  image_url TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  detector_model TEXT NOT NULL DEFAULT 'rt_detr',
  status TEXT NOT NULL DEFAULT 'uploaded',
  detected_count INTEGER NOT NULL DEFAULT 0,
  agent_run_id TEXT REFERENCES agent_runs(id),
  created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS detected_products (
  id TEXT PRIMARY KEY,
  upload_id TEXT NOT NULL REFERENCES inventory_image_uploads(id) ON DELETE CASCADE,
  bbox_x1 REAL NOT NULL,
  bbox_y1 REAL NOT NULL,
  bbox_x2 REAL NOT NULL,
  bbox_y2 REAL NOT NULL,
  detection_confidence REAL NOT NULL,
  ocr_text TEXT,
  top_matches_json TEXT NOT NULL DEFAULT '[]',
  selected_product_id TEXT REFERENCES products(id),
  is_unknown INTEGER NOT NULL DEFAULT 0,
  owner_action TEXT NOT NULL DEFAULT 'pending',
  owner_entered_qty REAL,
  owner_entered_price_paise INTEGER,
  owner_entered_expiry_date TEXT,
  created_at_utc TEXT NOT NULL,
  reviewed_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS owner_approvals (
  id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id),
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  original_value_json TEXT NOT NULL DEFAULT '{}',
  final_value_json TEXT NOT NULL DEFAULT '{}',
  notes TEXT,
  decided_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_inv_store ON store_inventory(store_id);
CREATE INDEX IF NOT EXISTS idx_sales_store_time ON sales(store_id, sold_at_utc);
CREATE INDEX IF NOT EXISTS idx_batches_store_exp ON stock_batches(store_id, expiry_date);
CREATE INDEX IF NOT EXISTS idx_comp_product ON competitor_prices(product_id);
"""


def seed_sqlite(db_path: Path) -> dict[str, int]:
    rng = random.Random(SEED)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SQLITE_SCHEMA)
    now_utc = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
    now_iso = now_utc.isoformat()

    users_rows = []
    stores_rows = []
    suppliers_rows = []

    # 1. 20 Store Owners + 20 Kirana Stores
    demo_pw = hash_password("KiranaDemo@2026")
    for idx in range(20):
        uid = det_uuid(f"owner-{idx}")
        email = "ramesh@lakshmikirana.in" if idx == 0 else f"owner{idx+1:02d}@kiranaconnect.in"
        full_name = "Ramesh Gowda" if idx == 0 else f"Store Owner {idx+1:02d}"
        phone = f"+91-98450{10000 + idx}"
        users_rows.append((uid, email, demo_pw, full_name, phone, "owner", "en", 1, 1, now_iso, now_iso))

        # Cluster first 10 stores closely around Indiranagar/Koramangala Bengaluru (< 1.8km apart) for nearby competition
        if idx < 10:
            base_city, base_state, base_pin, base_lat, base_lon = STORE_CITIES[0]
            lat = round(base_lat + rng.uniform(-0.011, 0.011), 6)
            lon = round(base_lon + rng.uniform(-0.011, 0.011), 6)
        else:
            base_city, base_state, base_pin, base_lat, base_lon = STORE_CITIES[(idx - 10) % len(STORE_CITIES)]
            lat = round(base_lat + rng.uniform(-0.025, 0.025), 6)
            lon = round(base_lon + rng.uniform(-0.025, 0.025), 6)

        sid = det_uuid(f"store-{idx}")
        store_code = f"KRN-{idx+1:03d}"
        is_verified = 1 if idx < 18 else 0
        stores_rows.append((
            sid, uid, store_code, STORE_NAMES[idx],
            f"{12 + idx}, Main Road, Sector {(idx % 5) + 1}",
            base_city, base_state, base_pin, lat, lon,
            is_verified, 1000, 1 if idx == 0 else 0, 1, now_iso, now_iso
        ))

        sup_id = det_uuid(f"supplier-{idx}")
        suppliers_rows.append((
            sup_id, sid, f"{base_city} Wholesale Distributors #{idx+1}",
            f"+91-80412{20000 + idx}", base_city, rng.choice([2, 3, 4, 5, 7]),
            250000, round(rng.uniform(0.89, 0.99), 3), 1, now_iso
        ))

    # 2. 50 Simulated Customers + 10 Delivery Partners
    customer_ids = []
    for idx in range(50):
        cid = det_uuid(f"customer-{idx}")
        customer_ids.append(cid)
        users_rows.append((
            cid, f"customer{idx+1:02d}@example.in", demo_pw,
            f"Customer {idx+1:02d}", f"+91-99001{30000 + idx}",
            "customer", rng.choice(["en", "hi", "kn"]), 1, 1, now_iso, now_iso
        ))

    for idx in range(10):
        did = det_uuid(f"delivery-{idx}")
        users_rows.append((
            did, f"partner{idx+1:02d}@example.in", demo_pw,
            f"Delivery Partner {idx+1:02d}", f"+91-97400{40000 + idx}",
            "delivery_partner", "en", 1, 1, now_iso, now_iso
        ))

    conn.executemany("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?,?)", users_rows)
    conn.executemany("INSERT INTO stores VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", stores_rows)
    conn.executemany("INSERT INTO suppliers VALUES (?,?,?,?,?,?,?,?,?,?)", suppliers_rows)

    # 3. 800 Common Indian Grocery Products across 9 Categories
    products_rows = []
    aliases_rows = []
    product_images_rows = []
    product_meta = []

    prod_counter = 0
    while prod_counter < 800:
        cat_name, exp_cat, base_items = CATEGORIES[prod_counter % len(CATEGORIES)]
        item_name = base_items[(prod_counter // len(CATEGORIES)) % len(base_items)]
        brand_list = BRANDS_BY_CATEGORY[cat_name]
        brand = brand_list[(prod_counter // 3) % len(brand_list)]
        variant_label, pack_val, pack_unit, unit_type, allow_loose = VARIANTS_AND_PACKS[prod_counter % len(VARIANTS_AND_PACKS)]

        is_loose = 1 if (allow_loose and brand == "Kirana Loose" and cat_name in ("Rice and grains", "Pulses and dals")) else 0
        if cat_name == "Packaged foods" and "Bread" in item_name:
            effective_exp_cat = "bakery"
        else:
            effective_exp_cat = exp_cat

        if is_loose:
            unit_type = "kg"
            pack_val = 1.0
            pack_unit = "kg"
            full_name = f"{item_name} (Loose per kg)"
        else:
            full_name = f"{brand} {item_name} {variant_label} {int(pack_val) if pack_val >= 1 else pack_val}{pack_unit}"

        mrp_rupees = rng.randint(20, 480)
        mrp_paise = mrp_rupees * 100
        cost_paise = int(round(mrp_paise * rng.uniform(0.72, 0.86)))
        pid = det_uuid(f"product-{prod_counter}")
        sku_code = f"SKU-{prod_counter+1:04d}"
        barcode = f"89010{prod_counter:08d}"

        products_rows.append((
            pid, sku_code, barcode, full_name, brand, variant_label,
            cat_name, item_name, unit_type, pack_val, pack_unit, is_loose,
            mrp_paise, cost_paise, 500 if cat_name in ("Rice and grains", "Pulses and dals", "Dairy") else 1200,
            effective_exp_cat, 1, now_iso, now_iso
        ))
        aliases_rows.append((
            det_uuid(f"alias-{prod_counter}"), pid, f"{item_name} {brand}", "en", "synthetic_seed", now_iso
        ))
        product_images_rows.append((
            det_uuid(f"pimg-{prod_counter}"), pid, None,
            f"/assets/placeholders/{sku_code.lower()}.svg",
            f"reference/{sku_code.lower()}.jpg",
            1, None, "dinov2-small", f"{brand} {item_name} {pack_val}{pack_unit}", now_iso
        ))
        product_meta.append((pid, sku_code, cat_name, effective_exp_cat, unit_type, mrp_paise, cost_paise, is_loose))
        prod_counter += 1

    conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", products_rows)
    conn.executemany("INSERT INTO product_aliases VALUES (?,?,?,?,?,?)", aliases_rows)
    conn.executemany("INSERT INTO product_images VALUES (?,?,?,?,?,?,?,?,?,?)", product_images_rows)

    # 4. Store Inventory, Stock Batches, Price History, Competitor Prices, and 6-Month Sales History
    inv_rows = []
    batch_rows = []
    price_hist_rows = []
    comp_rows = []
    sales_rows = []

    festival_by_day = {}
    for fest_name, offset in INDIAN_FESTIVALS:
        for d in range(max(0, offset - 2), min(180, offset + 2)):
            festival_by_day[d] = fest_name

    store0_lat, store0_lon = stores_rows[0][8], stores_rows[0][9]

    for s_idx, store_row in enumerate(stores_rows):
        sid = store_row[0]
        owner_uid = store_row[1]
        sup_id = suppliers_rows[s_idx][0]
        s_lat, s_lon = store_row[8], store_row[9]
        dist_from_store0 = haversine_km(store0_lat, store0_lon, s_lat, s_lon)

        # Store 0 gets 120 active SKUs; other stores get 45 active SKUs (overlapping top 45 for competition matching!)
        num_skus = 120 if s_idx == 0 else 45
        for p_idx in range(num_skus):
            pid, sku_code, cat_name, exp_cat, unit_type, mrp_paise, default_cost_paise, is_loose = product_meta[p_idx]
            inv_id = det_uuid(f"inv-{s_idx}-{p_idx}")

            # Ensure realistic mix: healthy, low-stock, out-of-stock
            if s_idx == 0 and p_idx % 15 == 0:
                avail_qty = 0.0
            elif s_idx == 0 and p_idx % 7 == 0:
                avail_qty = round(rng.uniform(2.0, 6.0), 3)
            else:
                avail_qty = round(rng.uniform(14.0, 85.0), 3) if is_loose else float(rng.randint(12, 95))

            reserved_qty = round(min(avail_qty, rng.uniform(0.0, 3.0)), 3) if avail_qty > 3 else 0.0
            incoming_qty = float(rng.choice([0, 0, 0, 12, 24]))
            # Selling price rounded to whole rupees, <= MRP
            selling_rupees = max(int(math.ceil(default_cost_paise / 100 * 1.12)), int(round((mrp_paise / 100) * rng.uniform(0.90, 1.0))))
            selling_price_paise = min(mrp_paise, selling_rupees * 100)

            reorder_pt = 12.0 if not is_loose else 15.0
            safety_stock = 5.0 if not is_loose else 6.0
            pack_size = 12.0 if not is_loose else 25.0

            inv_rows.append((
                inv_id, sid, pid, avail_qty, reserved_qty, incoming_qty, unit_type,
                selling_price_paise, default_cost_paise, mrp_paise, 1000,
                reorder_pt, safety_stock, sup_id, pack_size, 1, 0, 1, now_iso, now_iso
            ))

            price_hist_rows.append((
                det_uuid(f"ph-{s_idx}-{p_idx}"), sid, pid, selling_price_paise,
                selling_price_paise, mrp_paise, "initial_seed", None, owner_uid, now_iso
            ))

            # Stock batch with expiry date
            if exp_cat == "dairy":
                exp_days = rng.choice([2, 3, 5, 10, 14]) if (s_idx == 0 and p_idx % 3 == 0) else rng.randint(5, 25)
            elif exp_cat == "bakery":
                exp_days = rng.choice([1, 2, 4, 6])
            elif exp_cat == "snacks":
                exp_days = rng.choice([6, 12, 45, 90])
            else:
                exp_days = rng.randint(30, 240)

            exp_date = (now_utc.date() + timedelta(days=exp_days)).isoformat()
            mfg_date = (now_utc.date() - timedelta(days=rng.randint(10, 60))).isoformat()
            batch_status = "expiring_soon" if exp_days <= 7 and avail_qty > 0 else ("depleted" if avail_qty == 0 else "active")
            batch_id = det_uuid(f"batch-{s_idx}-{p_idx}")
            batch_rows.append((
                batch_id, inv_id, sid, pid, f"B-{sku_code}-{s_idx+1:02d}",
                max(avail_qty, 10.0), avail_qty, default_cost_paise,
                mfg_date, exp_date, 0, batch_status, now_iso
            ))

            # Competitor price observations from nearby stores (< 2.5km)
            if s_idx > 0 and p_idx < 45:
                comp_rows.append((
                    det_uuid(f"comp-{s_idx}-{p_idx}"), pid, sid, now_iso,
                    selling_price_paise, dist_from_store0, store_row[10], 1
                ))

            # 6 months (180 days) synthetic sales history (sampled daily/intermittent)
            # Store 0 gets dense 180-day series for its top 60 SKUs; other stores get weekly-sampled 180-day series
            step = 1 if (s_idx == 0 and p_idx < 60) else 3
            base_daily = rng.uniform(1.2, 6.5) if p_idx < 30 else rng.uniform(0.3, 2.2)
            for day_back in range(179, -1, -step):
                sale_dt = now_utc - timedelta(days=day_back, hours=rng.randint(1, 10))
                fest = festival_by_day.get(day_back)
                fest_mult = 1.45 if fest else 1.0
                wknd_mult = 1.25 if sale_dt.weekday() >= 5 else 1.0
                expected = base_daily * fest_mult * wknd_mult
                qty = round(max(0.5 if is_loose else 1.0, rng.gauss(expected, expected * 0.3)), 3 if is_loose else 0)
                if rng.random() < (0.82 if p_idx < 30 else 0.45):
                    total_rev = int(round(qty * selling_price_paise))
                    sales_rows.append((
                        det_uuid(f"sale-{s_idx}-{p_idx}-{day_back}"),
                        sid, pid, batch_id, rng.choice(customer_ids),
                        sale_dt.isoformat(), qty, unit_type,
                        selling_price_paise, default_cost_paise, total_rev,
                        1 if (day_back % 29 == 0) else 0, fest, 1
                    ))

    conn.executemany("INSERT INTO store_inventory VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", inv_rows)
    conn.executemany("INSERT INTO stock_batches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", batch_rows)
    conn.executemany("INSERT INTO price_history VALUES (?,?,?,?,?,?,?,?,?,?)", price_hist_rows)
    conn.executemany("INSERT INTO competitor_prices VALUES (?,?,?,?,?,?,?,?)", comp_rows)
    conn.executemany("INSERT INTO sales VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", sales_rows)

    conn.commit()

    counts = {}
    for tbl in [
        "users", "stores", "products", "product_images", "product_aliases",
        "suppliers", "store_inventory", "stock_batches", "sales",
        "demand_forecasts", "reorder_suggestions", "pricing_recommendations",
        "price_history", "competitor_prices", "agent_runs",
        "inventory_image_uploads", "detected_products", "owner_approvals",
    ]:
        counts[tbl] = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]

    conn.close()
    return counts


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "retail_connect.sqlite"
    summary = seed_sqlite(target)
    print(json.dumps({"sqlite_path": str(target), "seed": SEED, "table_counts": summary}, indent=2))
