# AI Powered Retail Connect — Objectives O1 and O2

Agentic AI-powered hyperlocal commerce platform for verified Kirana stores.

> **Current status: functional early MVP / beta, not production-complete.** This branch implements the core inventory review workflow, baseline demand forecasting and reorder approvals, and deterministic smart-pricing recommendations with owner approval. It does not claim trained retail-specific models or validated prediction accuracy.

## Objective 1 — Inventory Agent

### Implemented in this branch

- Shared master product/SKU catalogue with search, filtering and owner-created products.
- Store inventory listing and editing with quantity constraints, MRP and margin checks, version-based conflict detection, and price history.
- Batch and expiry ledger.
- Shelf-photo upload endpoint (JPEG/PNG/WebP, maximum 10 MB) with local file persistence.
- Generic YOLO11 object-region detection and crop-level EasyOCR.
- Owner-uploaded real SKU reference photos are embedded with openai/clip-vit-base-patch32 (512-D, L2-normalized) and stored in the existing PostgreSQL pgvector column.
- Detected image crops are embedded by CLIP, then the API retrieves the nearest SKU references directly from PostgreSQL/pgvector using cosine distance; OCR text matching is the fallback when references are absent or do not clear the preliminary similarity threshold.
- Unknown detections remain unassigned; they are not automatically forced to a SKU.
- Owner review UI can select/correct a SKU, confirm or reject a detection, enter the physically counted quantity, and optionally enter an expiry date and selling price.
- Only owner-confirmed quantities change inventory. Confirm/reject decisions are recorded in owner approvals.
- Moving-average, seven-day seasonal-naive and Croston-TSB intermittent-demand baselines.
- Expanding-window rolling-origin evaluation for all three baselines, reporting horizon-level MAE, WAPE and forecast bias.
- Reorder-point calculation using lead-time demand plus safety stock, with supplier pack-size rounding.
- Reorder suggestions support moving-average, seasonal-naive, Croston-TSB or per-SKU auto-selection by rolling-origin WAPE. Auto-selection requires at least three evaluation windows and falls back to moving average when evidence is insufficient.
- Reorder suggestions support owner accept/edit/reject. Approval does not automatically place a purchase order.

### Still incomplete for O1

- YOLO11 is currently a **generic pretrained object detector**, not a grocery-packaging detector trained/evaluated on the target product set.
- The CLIP reference-image path is implemented. A labelled evaluation utility now reports top-1 SKU accuracy, top-3 recall, mean reciprocal rank at 3, matching precision/recall, unknown-item rejection, and a threshold recommendation. No store reference-photo collection or labelled shelf-image evaluation data has been supplied yet, so the 0.58 cosine threshold remains provisional and no real-world accuracy claim is available.
- The model does not reliably count hidden, stacked or occluded products. Physical quantity confirmation remains mandatory.
- Advanced forecasting (LightGBM, N-HiTS), production model selection and external validation on representative real-store sales are not implemented. Current rolling-origin metrics reflect only the selected store's available history and can include synthetic seed data.
- There is no validated production dataset or measured real-world shelf detection/SKU matching accuracy. CLIP similarity scores are ranking signals, not calibrated probabilities.

## Objective 2 — Smart Pricing Agent

### Implemented in this branch

- Deterministic rule-based pricing engine.
- Recent verified competitor-price median (observations within 30 days and 2 km).
- Near-expiry markdown tiers and an excess-stock pressure adjustment.
- Whole-rupee recommendations with safeguards for MRP, minimum margin (unless clearance is explicitly enabled), a maximum 10% movement from the current price, and one approved price change per SKU per day.
- Owner accept/edit/reject workflow.
- Approved price changes update inventory, price history and owner-approval records.
- Generating a recommendation does not change a selling price automatically.
- No customer-level/personalized pricing.

### Still incomplete for O2

- No learned price-elasticity model or causal demand-response estimation.
- No validated sell-through uplift, revenue/margin uplift or markdown effectiveness evaluation.
- Demand-based price signals are not yet learned from historical price/quantity experiments. Current decisions are transparent business rules, not a trained pricing model.
- Competitor observations are synthetic in the demo dataset and must not be treated as live market prices.

## Architecture

- **Frontend PWA:** React 19, TypeScript, Vite, Tailwind CSS v4, React Router, TanStack Query and Recharts.
- **Integrated preview runtime:** Express + Node.js SQLite preview server on port 3000.
- **Agent API:** FastAPI, Pydantic v2, SQLAlchemy 2 and Alembic targeting PostgreSQL.
- **Vision service:** FastAPI, generic YOLO11 object-region detection and EasyOCR text extraction.
- **ML workspace:** reserved for later trained forecasting/pricing models and evaluation.

The repository retains the original Express/SQLite preview runtime and a separate FastAPI/PostgreSQL agent backend. The agent workflow described here uses the FastAPI service. The web Docker image builds the frontend with the FastAPI base URL.

## Docker setup — recommended

From the repository root in Windows PowerShell:

~~~powershell
Copy-Item .env.example .env
# Edit .env and set a unique JWT_SECRET before running the services.
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api python scripts/import_sqlite_seed.py
~~~

The seed importer reads the repository's synthetic SQLite database and inserts its rows into PostgreSQL. It is idempotent for existing primary keys and does not modify the SQLite source.

- Frontend: http://localhost:3000
- FastAPI Swagger docs: http://localhost:8000/docs
- Vision service docs: http://localhost:8001/docs
- API health: http://localhost:8000/api/v1/health

The API container reaches the vision container through the Compose service address. The browser reaches the API at localhost:8000.

## Seeded demo login

The synthetic seed includes this demo store owner:

- Email: ramesh@lakshmikirana.in
- Password: KiranaDemo@2026

Use this seeded account after the PostgreSQL import. Do not use it for real data.

## Main API routes

- POST /api/v1/auth/login and POST /api/v1/auth/register
- GET /api/v1/products and POST /api/v1/products
- GET /api/v1/stores/{store_id}/dashboard
- GET /api/v1/inventory/stores/{store_id}/inventory
- PATCH /api/v1/inventory/stores/{store_id}/inventory/{inventory_id}
- GET /api/v1/inventory/stores/{store_id}/images (owner-only review history)
- POST /api/v1/inventory/stores/{store_id}/products/{product_id}/reference-images (upload real SKU reference photo)
- GET /api/v1/inventory/stores/{store_id}/products/{product_id}/reference-images
- POST /api/v1/inventory/stores/{store_id}/images/analyze
- POST /api/v1/inventory/stores/{store_id}/images/{upload_id}/detections/{detection_id}/confirm
- POST /api/v1/inventory/stores/{store_id}/images/{upload_id}/detections/{detection_id}/reject
- GET /api/v1/forecasting/stores/{store_id}/products/{product_id}/forecast
- GET /api/v1/forecasting/stores/{store_id}/products/{product_id}/backtest
- POST /api/v1/forecasting/stores/{store_id}/reorder-suggestions/generate
- GET /api/v1/forecasting/stores/{store_id}/reorder-suggestions
- POST /api/v1/forecasting/stores/{store_id}/reorder-suggestions/{suggestion_id}/decision
- GET /api/v1/pricing/stores/{store_id}/competitor-comparison
- POST /api/v1/pricing/stores/{store_id}/recommendations/generate
- GET /api/v1/pricing/stores/{store_id}/recommendations
- POST /api/v1/pricing/stores/{store_id}/recommendations/{recommendation_id}/decision

All store-specific write actions require a valid owner JWT and verify store ownership.

## Verification

The GitHub Actions validation workflow checks:

- Frontend: TypeScript, production build and existing Node tests.
- API: unit tests plus PostgreSQL-backed integration tests covering Alembic migration, SQLite seed import, owner authentication, tenant isolation, inventory reads and shelf-photo review history.
- Vision: OCR fallback, CLIP cosine-ranking and labelled-evaluation calibration tests without downloading model weights. Full inference/reference-image embedding requires downloading the configured CLIP and YOLO weights on first use.

Run the checks locally:

~~~powershell
npm install
npm run lint
npm run build
npm test

cd services\api
$env:PYTHONPATH = "."
pip install -r requirements.txt
pytest -q tests

cd ..\vision
pip install pillow pytest
pytest -q test_pipeline.py
~~~

The vision utility tests do not verify full YOLO/EasyOCR inference. Full inference requires installing the vision requirements and downloading model weights on first use.

### Labelled image-matching evaluation

The evaluation utility consumes JSONL rows containing a query crop embedding, the expected SKU ID (or `null` for an unknown product), and the candidate catalogue's reference embeddings. It reports known-item top-1 accuracy, match precision/recall/F1, unknown-item rejection, and a calibrated threshold when both known and unknown labels are present.

Run from `services/vision` after preparing a labelled embedding JSONL file:

~~~powershell
python evaluate_matching.py .\data\labelled_shelf_embeddings.jsonl --output .\reports\matching_calibration.json
~~~

Each sample must contain `query_id`, `expected_product_id`, a 512-value `query_embedding`, and a `catalogue` list whose products include `product_id`, `sku_code`, and `reference_embeddings` (a list of 512-value vectors). Set `expected_product_id` to JSON `null` for a genuinely unknown/unlisted item. Use representative lighting, angles, packaging variants and unknown products. Keep a separate held-out test set: calibration-set metrics are not final test accuracy. The report explicitly treats cosine similarity as a ranking score, not a probability.

### Labelled shelf-region detection evaluation

The region evaluator accepts one JSONL row per image with `image_id`, normalized `ground_truth_boxes` (`[x1, y1, x2, y2]`) and `predicted_boxes` (each with `bbox`, `confidence`, and optional `label`). It reports class-agnostic precision, recall, F1 and AP@IoU0.50 for candidate object regions. This does not measure SKU identity, class correctness or quantity estimation.

Run from `services/vision`:

~~~powershell
python evaluate_detections.py .\data\labelled_shelf_boxes.jsonl --confidence 0.25 --iou 0.50 --output .\reports\region_detection_metrics.json
~~~

Use the AP result only as a class-agnostic object-region localization measure; do not report it as SKU mAP. Real held-out shelf photos and labelled boxes are still needed before the generic YOLO detector can be considered validated.



## Important security, data and deployment limitations

- The current authentication hash deliberately matches the existing demo SQLite preview's fixed-salt SHA-256 scheme. **It is not safe for real user accounts.** Replace it with Argon2id/bcrypt/scrypt and migrate both runtimes before production.
- Set a strong unique JWT_SECRET in .env. The browser frontend does not receive the secret.
- New store registration leaves the store unverified and uses placeholder Bengaluru coordinates. Replace these with verified coordinates before enabling real location-based comparisons.
- Shelf photos are stored locally under services/api/uploads (mounted into the API container). Configure private durable object storage, access controls and retention/deletion policies before handling real store imagery.
- Use synthetic data for development. Synthetic competitor observations, sales history and seed accounts are not evidence of real-world performance.
- The repository does not yet declare a project licence. Review the licenses of all detector packages and model weights before redistribution or commercial deployment.
