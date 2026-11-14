"""OCR-assisted shelf-photo analysis with fail-closed SKU matching.

YOLO's generic COCO labels locate candidate object regions; OCR text is compared
to the supplied SKU catalogue. This is not a retail-trained detector and it
does not estimate hidden/stacked stock quantities. Owner quantity entry remains
mandatory.
"""
from __future__ import annotations

import os
import re
from difflib import SequenceMatcher
from functools import lru_cache
from io import BytesIO
from typing import Any

from PIL import Image


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def match_catalogue(ocr_text: str, catalogue: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    """Rank catalogue rows by OCR token overlap and character similarity."""
    query = _normalise(ocr_text)
    if not query:
        return []
    q_tokens = set(query.split())
    ranked: list[dict[str, Any]] = []
    for item in catalogue:
        searchable = _normalise(" ".join(str(item.get(k, "")) for k in (
            "sku_code", "barcode", "brand", "name", "variant"
        )))
        tokens = set(searchable.split())
        overlap = len(q_tokens & tokens) / max(1, len(q_tokens))
        ratio = SequenceMatcher(None, query, searchable).ratio()
        score = min(1.0, 0.75 * overlap + 0.25 * ratio)
        if score >= 0.24:
            ranked.append({
                "product_id": str(item.get("product_id", "")),
                "sku_code": str(item.get("sku_code", "")),
                "name": str(item.get("name", "")),
                "brand": str(item.get("brand", "")),
                "score": round(score, 4),
            })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:limit]


@lru_cache(maxsize=1)
def _detector():
    from ultralytics import YOLO

    weights = os.getenv("VISION_DETECTOR_WEIGHTS", "yolo11n.pt")
    return YOLO(weights)


@lru_cache(maxsize=1)
def _ocr_reader():
    import easyocr

    languages = [x.strip() for x in os.getenv("VISION_OCR_LANGUAGES", "en").split(",") if x.strip()]
    return easyocr.Reader(languages or ["en"], gpu=False)


def analyze_image(image_bytes: bytes, catalogue: list[dict[str, Any]]) -> dict[str, Any]:
    """Run generic object detection, crop OCR and cautious SKU text matching."""
    import numpy as np

    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    width, height = image.size
    if width < 64 or height < 64 or width * height > 25_000_000:
        raise ValueError("Image dimensions are outside supported limits")
    detector = _detector()
    reader = _ocr_reader()
    result = detector.predict(source=image, conf=0.25, verbose=False)[0]
    detections = []
    for box in result.boxes:
        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
        x1i, y1i = max(0, int(x1)), max(0, int(y1))
        x2i, y2i = min(width, int(x2)), min(height, int(y2))
        if x2i <= x1i or y2i <= y1i:
            continue
        crop = image.crop((x1i, y1i, x2i, y2i))
        texts = reader.readtext(np.asarray(crop), detail=0, paragraph=False)
        ocr_text = " ".join(str(t) for t in texts).strip()
        matches = match_catalogue(ocr_text, catalogue)
        class_id = int(box.cls[0].item())
        label = result.names.get(class_id, str(class_id))
        detections.append({
            "bbox": [
                round(x1i / width, 5), round(y1i / height, 5),
                round(x2i / width, 5), round(y2i / height, 5),
            ],
            "detector_label": label,
            "detection_confidence": round(float(box.conf[0].item()), 4),
            "ocr_text": ocr_text,
            "top_matches": matches,
            "is_unknown": not bool(matches),
            "matching_method": "ocr_token_similarity",
            "quantity_requires_owner_confirmation": True,
        })
    return {
        "detector": os.getenv("VISION_DETECTOR_WEIGHTS", "yolo11n.pt"),
        "detections": detections,
        "detection_count": len(detections),
        "matching_method": "ocr_token_similarity",
        "embedding_matching_enabled": False,
        "stock_quantity_inferred": False,
        "owner_quantity_confirmation_required": True,
    }
