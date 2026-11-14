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
- Expanding-window rolling-origin evaluation for all three baselines, reporting horizon-level MAE, WAPE and forecast bias. Synthetic seed sales are excluded from this accuracy endpoint by default; they can be explicitly included for development checks and are marked in the report.
- Reorder-point calculation using lead-time demand plus safety stock, with supplier pack-size rounding.
- Reorder suggestions support moving-average, seasonal-naive, Croston-TSB or per-SKU auto-selection by rolling-origin WAPE. Auto-selection requires at least three evaluation windows and falls back to moving average when evidence is insufficient.
- Reorder suggestions support owner accept/edit/reject. Approval does not automatically place a purchase order.

### Still incomplete for O1

- YOLO11 is currently a **generic pretrained object detector**, not a grocery-packaging detector trained/evaluated on the target product set.
- The CLIP reference-image path is implemented. A labelled evaluation utility now reports top-1 SKU accuracy, top-3 recall, mean reciprocal rank at 3, matching precision/recall, unknown-item rejection, and a threshold recommendation. No store reference-photo collection or labelled shelf-image evaluation data has been supplied yet, so the 0.58 cosine threshold remains provisional and no real-world accuracy claim is available.
- The model does not reliably count hidden, stacked or occluded products. Physical quantity confirmation remains mandatory.
- Advanced forecasting (LightGBM, N-HiTS), production model selection and external validation on representative real-store sales are not implemented. Current rolling-origin metrics reflect only the selected store's non-synthetic sales by default. A development-only query option can include synthetic rows, which are explicitly marked.
- There is no validated production dataset or measured real-world shelf detection/SKU matching accuracy. CLIP similarity scores are ranking signals, not calibrated probabilities.

## Objective 2 — Smart Pricing Agent

### Implemented in this branch

- Deterministic rule-based pricing engine.
- Competitor comparison uses only the latest **non-synthetic, verified price per verified peer store and SKU**, within 2 km and the previous 30 days. Repeated observations from one peer cannot overweight the median; unverified, synthetic, stale, future, distant and same-store observations are excluded.
- A transparent real-sales demand-trend signal compares the latest 7 days with the preceding 28-day sales baseline. Ratios of at least 1.25 produce a +3% signal, ratios at or below 0.75 produce a -3% signal, and intermediate/insufficient history remains neutral. Synthetic sales are excluded.
- Near-expiry markdown tiers and a bounded excess-stock pressure adjustment.
- Whole-rupee recommendations with MRP and gross-margin-on-selling-price safeguards (unless clearance is explicitly enabled), plus a maximum +/-10% movement for any actual daily price change.
- One actual price change per SKU per India-local calendar day. The same guardrail is shared by pricing-agent approvals, manual inventory edits and shelf-photo review price edits. No-op approvals do not consume the daily change allowance.
- Owner accept/edit/reject workflow. Every approved price change updates inventory, price history and owner-approval records.
- Generating a recommendation does not change a selling price automatically.
- No customer-level/personalized pricing.

### Still incomplete for O2

- No learned price-elasticity model, causal demand-response estimation or controlled price/quantity experiment analysis. The current 7d/28d signal is a transparent trend heuristic, not price elasticity.
- No validated sell-through uplift, revenue/margin uplift or markdown-effectiveness evaluation.
- No live competitor collection or external market-data integration is included. Demo synthetic competitor observations are excluded from the real-peer comparison and pricing recommendation path; verified real observations must be supplied by an independent trusted process.
- The heuristic thresholds and markdown tiers have not yet been calibrated against held-out store-level revenue and margin outcomes.

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
- GET /api/v1/forecasting/stores/{store_id}/products/{product_id}/backtest (real sales only by default; use `include_synthetic=true` for development checks)
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

To build embedding JSONL directly from real image files, first prepare a manifest with paths relative to the manifest file:

~~~json
{"query_id":"shelf-001-crop-01","query_image":"queries/crop-01.jpg","expected_product_id":"product-uuid-1","catalogue":[{"product_id":"product-uuid-1","sku_code":"SKU-001","name":"Example product","brand":"Example brand","reference_images":["references/SKU-001-front.jpg","references/SKU-001-back.jpg"]},{"product_id":"product-uuid-2","sku_code":"SKU-002","name":"Another product","brand":"Another brand","reference_images":["references/SKU-002-front.jpg"]}]}
{"query_id":"shelf-001-crop-02","query_image":"queries/crop-02.jpg","expected_product_id":null,"catalogue":[{"product_id":"product-uuid-1","sku_code":"SKU-001","name":"Example product","brand":"Example brand","reference_images":["references/SKU-001-front.jpg"]}]}
~~~

Then run:

~~~powershell
python prepare_matching_eval.py .\data\matching_manifest.jsonl --output .\data\matching_embeddings.jsonl
python evaluate_matching.py .\data\matching_embeddings.jsonl --output .\reports\matching_calibration.json
~~~

The preparation step embeds repeated reference files once and rejects a query image that is also listed as its own SKU reference. For held-out evaluation, split by original photo/session (and preferably store) before preparing the manifest; separate crops from the same shelf photo are not independent test samples.

### Labelled shelf-region detection evaluation

The region evaluator accepts one JSONL row per image with `image_id`, normalized `ground_truth_boxes` (`[x1, y1, x2, y2]`) and `predicted_boxes` (each with `bbox`, `confidence`, and optional `label`). It reports class-agnostic precision, recall, F1 and AP@IoU0.50 for candidate object regions. This does not measure SKU identity, class correctness or quantity estimation.

Run from `services/vision`:

~~~powershell
python evaluate_detections.py .\data\labelled_shelf_boxes.jsonl --confidence 0.25 --iou 0.50 --output .\reports\region_detection_metrics.json
~~~

Use the AP result only as a class-agnostic object-region localization measure; do not report it as SKU mAP. Real held-out shelf photos and labelled boxes are still needed before the generic YOLO detector can be considered validated.



## Important security, data and deployment limitations

- New owner passwords use Argon2id. Legacy demo SHA-256 hashes are upgraded to Argon2id after a successful login; the seeded demo account remains demo-only and must not be used as a production credential.
- Set a strong unique JWT_SECRET in .env. The browser frontend does not receive the secret.
- New store registration leaves the store unverified and uses placeholder Bengaluru coordinates. Replace these with verified coordinates before enabling real location-based comparisons.
- Shelf photos are stored locally under services/api/uploads (mounted into the API container). Configure private durable object storage, access controls and retention/deletion policies before handling real store imagery.
- Use synthetic data for development. Synthetic competitor observations, sales history and seed accounts are not evidence of real-world performance.
- The repository does not yet declare a project licence. Review the licenses of all detector packages and model weights before redistribution or commercial deployment.
