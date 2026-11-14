from datetime import datetime, timezone
import json
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from pipeline import analyze_image, embed_image_bytes, match_catalogue, DEFAULT_EMBEDDING_MODEL

app = FastAPI(
    title="AI Powered Retail Connect - Vision Service",
    version="0.3.0",
    description="Generic YOLO regions, EasyOCR, and CLIP image-reference matching.",
)


class VisionHealth(BaseModel):
    status: str
    service: str
    detectors_supported: list[str]
    stage: str
    timestamp_utc: datetime
    embedding_matching_enabled: bool
    embedding_model: str


@app.get("/health", response_model=VisionHealth)
def health() -> VisionHealth:
    return VisionHealth(
        status="ok",
        service="retail-connect-vision",
        detectors_supported=["yolo11_generic"],
        stage="clip_reference_matching_beta",
        timestamp_utc=datetime.now(timezone.utc),
        embedding_matching_enabled=True,
        embedding_model=os.getenv("VISION_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
    )


@app.post("/embed")
async def embed_reference_image(file: UploadFile = File(...)) -> dict:
    """Return an L2-normalized 512-D CLIP image embedding for a SKU reference."""
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG and WebP images are supported")
    raw = await file.read(10 * 1024 * 1024 + 1)
    if not raw or len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be non-empty and no larger than 10 MB")
    try:
        embedding, model_name = await run_in_threadpool(embed_image_bytes, raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"Vision dependency unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"CLIP image embedding unavailable: {exc}")
    return {
        "embedding": embedding,
        "dimension": len(embedding),
        "model": model_name,
        "normalization": "l2",
    }


@app.post("/analyze")
async def analyze_shelf_photo(
    file: UploadFile = File(...),
    catalogue_json: str = Form(...),
    use_visual_embeddings: bool = Form(default=False),
) -> dict:
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG and WebP images are supported")
    raw = await file.read(10 * 1024 * 1024 + 1)
    if not raw or len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be non-empty and no larger than 10 MB")
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
        return await run_in_threadpool(analyze_image, raw, catalogue, use_visual_embeddings)
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
        "method": "ocr_text_similarity",
        "embedding_matching_enabled": False,
    }
