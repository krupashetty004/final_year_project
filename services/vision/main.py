from datetime import datetime, timezone
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="AI Powered Retail Connect - Vision Service",
    version="0.1.0",
    description="Dedicated Computer Vision Microservice (RT-DETR, YOLO11 baseline, DINOv2/CLIP embeddings, EasyOCR).",
)


class VisionHealth(BaseModel):
    status: str
    service: str
    detectors_supported: list[str]
    stage: str
    timestamp_utc: datetime


@app.get("/health", response_model=VisionHealth)
def health() -> VisionHealth:
    return VisionHealth(
        status="ok",
        service="retail-connect-vision",
        detectors_supported=["rt_detr", "yolo11"],
        stage="stage-1-foundation",
        timestamp_utc=datetime.now(timezone.utc),
    )
