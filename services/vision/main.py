from datetime import datetime, timezone
import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from pipeline import analyze_image, match_catalogue

app = FastAPI(
    title="AI Powered Retail Connect - Vision Service",
    version="0.2.0",
    description="YOLO object-region detection plus OCR-assisted catalogue candidate ranking.",
)


class VisionHealth(BaseModel):
    status: str
    service: str
    detectors_supported: list[str]
    stage: str
    timestamp_utc: datetime
    embedding_matching_enabled: bool


@app.get("/health", response_model=VisionHealth)
def health() -> VisionHealth:
    return VisionHealth(
        status="ok",
        service="retail-connect-vision",
        detectors_supported=["yolo11_generic"],
        stage="ocr_assisted_beta",
        timestamp_utc=datetime.now(timezone.utc),
        embedding_matching_enabled=False,
    )


@app.post("/analyze")
async def analyze_shelf_photo(
    file: UploadFile = File(...),
    catalogue_json: str = Form(...),
) -> dict:
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG and WebP images are supported")
    raw = await file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds the 10 MB limit")
    try:
        catalogue = json.loads(catalogue_json)
        if not isinstance(catalogue, list) or len(catalogue) > 2000:
            raise ValueError("catalogue_json must be a list with at most 2,000 products")
        for item in catalogue:
            if not isinstance(item, dict) or not item.get("product_id") or not item.get("sku_code"):
                raise ValueError("Each catalogue item must include product_id and sku_code")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid catalogue: {exc}")
    try:
        return await run_in_threadpool(analyze_image, raw, catalogue)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"Vision dependency unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Vision inference unavailable: {exc}")


class CatalogueMatchRequest(BaseModel):
    ocr_text: str
    catalogue: list[dict]


@app.post("/match-catalogue")
def match_catalogue_endpoint(payload: CatalogueMatchRequest) -> dict:
    return {
        "matches": match_catalogue(payload.ocr_text, payload.catalogue),
        "method": "ocr_token_similarity",
        "embedding_matching_enabled": False,
    }
