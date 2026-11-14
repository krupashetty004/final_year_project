-- ==============================================================================
-- AI POWERED RETAIL CONNECT - INITIAL POSTGRESQL / SUPABASE SCHEMA (STAGE 1)
-- ==============================================================================
-- Rules enforced at DB level:
--   1. UUID primary keys across all 18 core tables
--   2. Money stored strictly in integer paise (*_paise)
--   3. Quantities stored as NUMERIC(12,3) with explicit unit_type
--   4. Timestamps stored in UTC (TIMESTAMPTZ)
--   5. Unique (store_id, product_id) in store_inventory
--   6. reserved_qty <= available_qty enforced via CHECK constraint
--   7. selling_price_paise <= mrp_paise enforced via CHECK constraint
--   8. Optimistic locking via store_inventory.version
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";
-- PostGIS is available on Supabase & postgis/postgis images; guarded for vanilla pgvector images
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS "postgis";
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'PostGIS extension not available in this container; continuing with numeric lat/lon columns.';
END $$;

-- 1. users
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  full_name VARCHAR(160) NOT NULL,
  phone VARCHAR(24),
  role VARCHAR(32) NOT NULL CHECK (role IN ('owner', 'staff', 'admin', 'customer', 'delivery_partner')),
  preferred_language VARCHAR(8) NOT NULL DEFAULT 'en',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- 2. stores
CREATE TABLE IF NOT EXISTS stores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  store_code VARCHAR(32) NOT NULL UNIQUE,
  name VARCHAR(180) NOT NULL,
  address TEXT NOT NULL,
  city VARCHAR(100) NOT NULL,
  state VARCHAR(100) NOT NULL,
  pincode VARCHAR(12) NOT NULL,
  latitude DOUBLE PRECISION NOT NULL,
  longitude DOUBLE PRECISION NOT NULL,
  is_verified BOOLEAN NOT NULL DEFAULT FALSE,
  default_min_margin_bps INTEGER NOT NULL DEFAULT 1000 CHECK (default_min_margin_bps >= 0 AND default_min_margin_bps <= 9000),
  clearance_below_margin_allowed BOOLEAN NOT NULL DEFAULT FALSE,
  is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_stores_owner ON stores(owner_id);
CREATE INDEX IF NOT EXISTS idx_stores_city_verified ON stores(city, is_verified);

-- 3. products (Shared master product identity across stores)
CREATE TABLE IF NOT EXISTS products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sku_code VARCHAR(64) NOT NULL UNIQUE,
  barcode VARCHAR(64),
  name VARCHAR(255) NOT NULL,
  brand VARCHAR(120) NOT NULL,
  variant VARCHAR(120) NOT NULL DEFAULT '',
  category VARCHAR(80) NOT NULL,
  subcategory VARCHAR(80) NOT NULL DEFAULT '',
  unit_type VARCHAR(16) NOT NULL CHECK (unit_type IN ('pcs', 'kg', 'g', 'l', 'ml', 'pack')),
  pack_size_value NUMERIC(10,3) NOT NULL CHECK (pack_size_value > 0),
  pack_size_unit VARCHAR(16) NOT NULL,
  is_loose_commodity BOOLEAN NOT NULL DEFAULT FALSE,
  mrp_paise INTEGER NOT NULL CHECK (mrp_paise > 0),
  default_cost_paise INTEGER NOT NULL CHECK (default_cost_paise >= 0 AND default_cost_paise <= mrp_paise),
  gst_bps INTEGER NOT NULL DEFAULT 500,
  expiry_category VARCHAR(32) NOT NULL CHECK (expiry_category IN ('dairy', 'bakery', 'snacks', 'grocery', 'other')),
  is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON products USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_brand_trgm ON products USING gin (brand gin_trgm_ops);

-- 4. product_images
CREATE TABLE IF NOT EXISTS product_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  store_id UUID REFERENCES stores(id) ON DELETE SET NULL,
  image_url TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  is_reference BOOLEAN NOT NULL DEFAULT TRUE,
  embedding VECTOR(512),
  embedding_model VARCHAR(64) NOT NULL DEFAULT 'dinov2-small',
  ocr_extracted_text TEXT,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_product_images_product ON product_images(product_id);

-- 5. product_aliases
CREATE TABLE IF NOT EXISTS product_aliases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  alias_text VARCHAR(255) NOT NULL,
  language_code VARCHAR(8) NOT NULL DEFAULT 'en',
  source VARCHAR(32) NOT NULL DEFAULT 'catalogue',
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_product_aliases_product ON product_aliases(product_id);
CREATE INDEX IF NOT EXISTS idx_product_aliases_text_trgm ON product_aliases USING gin (alias_text gin_trgm_ops);

-- 9. suppliers (declared before store_inventory FK)
CREATE TABLE IF NOT EXISTS suppliers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
  name VARCHAR(180) NOT NULL,
  contact_phone VARCHAR(24),
  city VARCHAR(100) NOT NULL,
  lead_time_days INTEGER NOT NULL CHECK (lead_time_days >= 1 AND lead_time_days <= 60),
  min_order_value_paise INTEGER NOT NULL DEFAULT 0,
  reliability_score NUMERIC(4,3) NOT NULL DEFAULT 0.950,
  is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- 6. store_inventory
CREATE TABLE IF NOT EXISTS store_inventory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  available_qty NUMERIC(12,3) NOT NULL CHECK (available_qty >= 0),
  reserved_qty NUMERIC(12,3) NOT NULL DEFAULT 0 CHECK (reserved_qty >= 0 AND reserved_qty <= available_qty),
  incoming_qty NUMERIC(12,3) NOT NULL DEFAULT 0 CHECK (incoming_qty >= 0),
  unit_type VARCHAR(16) NOT NULL CHECK (unit_type IN ('pcs', 'kg', 'g', 'l', 'ml', 'pack')),
  selling_price_paise INTEGER NOT NULL CHECK (selling_price_paise > 0),
  cost_price_paise INTEGER NOT NULL CHECK (cost_price_paise >= 0),
  mrp_paise INTEGER NOT NULL CHECK (selling_price_paise <= mrp_paise),
  min_margin_bps INTEGER NOT NULL DEFAULT 1000 CHECK (min_margin_bps >= 0),
  reorder_point_qty NUMERIC(12,3) NOT NULL DEFAULT 0,
  safety_stock_qty NUMERIC(12,3) NOT NULL DEFAULT 0,
  supplier_id UUID REFERENCES suppliers(id) ON DELETE SET NULL,
  supplier_pack_size NUMERIC(12,3) NOT NULL DEFAULT 1 CHECK (supplier_pack_size > 0),
  is_listed BOOLEAN NOT NULL DEFAULT TRUE,
  clearance_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  version INTEGER NOT NULL DEFAULT 1,
  last_price_changed_at_utc TIMESTAMPTZ,
  updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  CONSTRAINT uq_store_inventory_store_product UNIQUE (store_id, product_id)
);
CREATE INDEX IF NOT EXISTS idx_store_inventory_store ON store_inventory(store_id);
CREATE INDEX IF NOT EXISTS idx_store_inventory_product ON store_inventory(product_id);

-- 7. stock_batches
CREATE TABLE IF NOT EXISTS stock_batches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  store_inventory_id UUID NOT NULL REFERENCES store_inventory(id) ON DELETE CASCADE,
  store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  batch_code VARCHAR(64) NOT NULL,
  initial_qty NUMERIC(12,3) NOT NULL CHECK (initial_qty >= 0),
  remaining_qty NUMERIC(12,3) NOT NULL CHECK (remaining_qty >= 0),
  cost_price_paise INTEGER NOT NULL CHECK (cost_price_paise >= 0),
  manufactured_date DATE,
  expiry_date DATE,
  clearance_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  status VARCHAR(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expiring_soon', 'expired', 'depleted')),
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_stock_batches_store_expiry ON stock_batches(store_id, expiry_date);

-- 8. sales
CREATE TABLE IF NOT EXISTS sales (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  batch_id UUID REFERENCES stock_batches(id) ON DELETE SET NULL,
  customer_id UUID REFERENCES users(id) ON DELETE SET NULL,
  sold_at_utc TIMESTAMPTZ NOT NULL,
  quantity NUMERIC(12,3) NOT NULL CHECK (quantity > 0),
  unit_type VARCHAR(16) NOT NULL,
  unit_selling_price_paise INTEGER NOT NULL CHECK (unit_selling_price_paise > 0),
  unit_cost_paise INTEGER NOT NULL CHECK (unit_cost_paise >= 0),
  total_revenue_paise INTEGER NOT NULL CHECK (total_revenue_paise >= 0),
  was_promotional BOOLEAN NOT NULL DEFAULT FALSE,
  festival_tag VARCHAR(64),
  is_synthetic BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_sales_store_product_time ON sales(store_id, product_id, sold_at_utc);

-- 15. agent_runs (declared before forecast/reorder/pricing/upload FKs)
CREATE TABLE IF NOT EXISTS agent_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_type VARCHAR(48) NOT NULL CHECK (agent_type IN ('inventory_vision', 'demand_forecast', 'reorder_planner', 'smart_pricing')),
  store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
  model_name VARCHAR(120) NOT NULL,
  model_version VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL CHECK (status IN ('running', 'completed', 'fallback_completed', 'failed')),
  input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  output_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
  fallback_reason TEXT,
  started_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  completed_at_utc TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_store_type ON agent_runs(store_id, agent_type, started_at_utc DESC);

-- 10. demand_forecasts
CREATE TABLE IF NOT EXISTS demand_forecasts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  forecast_date DATE NOT NULL,
  horizon_days INTEGER NOT NULL CHECK (horizon_days >= 1),
  model_name VARCHAR(48) NOT NULL CHECK (model_name IN ('seasonal_naive', 'moving_average', 'croston_tsb', 'lightgbm', 'nhits')),
  predicted_qty NUMERIC(12,3) NOT NULL CHECK (predicted_qty >= 0),
  lower_bound_qty NUMERIC(12,3) NOT NULL CHECK (lower_bound_qty >= 0),
  upper_bound_qty NUMERIC(12,3) NOT NULL CHECK (upper_bound_qty >= 0),
  forecast_error_sigma NUMERIC(12,4) NOT NULL DEFAULT 0,
  wape_score NUMERIC(8,4),
  mae_score NUMERIC(10,4),
  rmse_score NUMERIC(10,4),
  mase_score NUMERIC(8,4),
  agent_run_id UUID REFERENCES agent_runs(id) ON DELETE SET NULL,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_demand_forecasts_lookup ON demand_forecasts(store_id, product_id, forecast_date);

-- 11. reorder_suggestions
CREATE TABLE IF NOT EXISTS reorder_suggestions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  supplier_id UUID REFERENCES suppliers(id) ON DELETE SET NULL,
  current_available_qty NUMERIC(12,3) NOT NULL,
  incoming_qty NUMERIC(12,3) NOT NULL,
  expected_lead_time_demand_qty NUMERIC(12,3) NOT NULL,
  safety_stock_qty NUMERIC(12,3) NOT NULL,
  reorder_point_qty NUMERIC(12,3) NOT NULL,
  supplier_pack_size NUMERIC(12,3) NOT NULL,
  raw_suggested_qty NUMERIC(12,3) NOT NULL,
  rounded_suggested_qty NUMERIC(12,3) NOT NULL CHECK (rounded_suggested_qty >= 0),
  estimated_cost_paise INTEGER NOT NULL CHECK (estimated_cost_paise >= 0),
  explanation TEXT NOT NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'edited', 'rejected')),
  owner_final_qty NUMERIC(12,3),
  agent_run_id UUID REFERENCES agent_runs(id) ON DELETE SET NULL,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  decided_at_utc TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_reorder_suggestions_store_status ON reorder_suggestions(store_id, status);

-- 12. pricing_recommendations
CREATE TABLE IF NOT EXISTS pricing_recommendations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  batch_id UUID REFERENCES stock_batches(id) ON DELETE SET NULL,
  current_price_paise INTEGER NOT NULL CHECK (current_price_paise > 0),
  mrp_paise INTEGER NOT NULL CHECK (mrp_paise > 0),
  cost_price_paise INTEGER NOT NULL CHECK (cost_price_paise >= 0),
  nearby_median_price_paise INTEGER,
  demand_signal_price_paise INTEGER,
  expiry_discount_pct NUMERIC(5,2) NOT NULL DEFAULT 0,
  competition_signal_price_paise INTEGER,
  stock_pressure_factor NUMERIC(6,3) NOT NULL DEFAULT 1.000,
  recommended_price_paise INTEGER NOT NULL CHECK (recommended_price_paise > 0 AND recommended_price_paise <= mrp_paise),
  expected_margin_bps INTEGER NOT NULL,
  expected_sell_through_delta_pct NUMERIC(6,2) NOT NULL DEFAULT 0,
  explanation TEXT NOT NULL,
  constraints_passed BOOLEAN NOT NULL DEFAULT TRUE,
  constraint_notes TEXT,
  status VARCHAR(24) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'edited', 'rejected', 'expired')),
  owner_final_price_paise INTEGER,
  agent_run_id UUID REFERENCES agent_runs(id) ON DELETE SET NULL,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  decided_at_utc TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_pricing_recs_store_status ON pricing_recommendations(store_id, status);

-- 13. price_history
CREATE TABLE IF NOT EXISTS price_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  old_price_paise INTEGER NOT NULL CHECK (old_price_paise > 0),
  new_price_paise INTEGER NOT NULL CHECK (new_price_paise > 0),
  mrp_paise INTEGER NOT NULL CHECK (new_price_paise <= mrp_paise),
  change_source VARCHAR(48) NOT NULL CHECK (change_source IN ('owner_manual', 'pricing_agent_approved', 'pricing_agent_edited', 'initial_seed')),
  pricing_recommendation_id UUID REFERENCES pricing_recommendations(id) ON DELETE SET NULL,
  changed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  changed_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_price_history_store_product ON price_history(store_id, product_id, changed_at_utc DESC);

-- 14. competitor_prices
CREATE TABLE IF NOT EXISTS competitor_prices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  competitor_store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  observed_at_utc TIMESTAMPTZ NOT NULL,
  selling_price_paise INTEGER NOT NULL CHECK (selling_price_paise > 0),
  distance_km NUMERIC(6,3) NOT NULL CHECK (distance_km >= 0),
  is_verified BOOLEAN NOT NULL DEFAULT TRUE,
  is_synthetic BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_competitor_prices_product ON competitor_prices(product_id, observed_at_utc DESC);

-- 16. inventory_image_uploads
CREATE TABLE IF NOT EXISTS inventory_image_uploads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  uploaded_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  image_url TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  detector_model VARCHAR(24) NOT NULL DEFAULT 'rt_detr' CHECK (detector_model IN ('rt_detr', 'yolo11')),
  status VARCHAR(32) NOT NULL DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'processing', 'ready_for_review', 'confirmed', 'failed')),
  detected_count INTEGER NOT NULL DEFAULT 0,
  agent_run_id UUID REFERENCES agent_runs(id) ON DELETE SET NULL,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- 17. detected_products
CREATE TABLE IF NOT EXISTS detected_products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  upload_id UUID NOT NULL REFERENCES inventory_image_uploads(id) ON DELETE CASCADE,
  bbox_x1 NUMERIC(8,4) NOT NULL,
  bbox_y1 NUMERIC(8,4) NOT NULL,
  bbox_x2 NUMERIC(8,4) NOT NULL,
  bbox_y2 NUMERIC(8,4) NOT NULL,
  detection_confidence NUMERIC(5,4) NOT NULL,
  ocr_text TEXT,
  top_matches_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  selected_product_id UUID REFERENCES products(id) ON DELETE SET NULL,
  is_unknown BOOLEAN NOT NULL DEFAULT FALSE,
  owner_action VARCHAR(24) NOT NULL DEFAULT 'pending' CHECK (owner_action IN ('pending', 'confirmed', 'corrected', 'rejected')),
  owner_entered_qty NUMERIC(12,3),
  owner_entered_price_paise INTEGER,
  owner_entered_expiry_date DATE,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  reviewed_at_utc TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_detected_products_upload ON detected_products(upload_id);

-- 18. owner_approvals
CREATE TABLE IF NOT EXISTS owner_approvals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  entity_type VARCHAR(48) NOT NULL CHECK (entity_type IN ('reorder_suggestion', 'pricing_recommendation', 'detected_product')),
  entity_id UUID NOT NULL,
  decision VARCHAR(24) NOT NULL CHECK (decision IN ('accepted', 'edited', 'rejected', 'confirmed')),
  original_value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  final_value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  notes TEXT,
  decided_at_utc TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_owner_approvals_store_time ON owner_approvals(store_id, decided_at_utc DESC);
