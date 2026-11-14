"""Shelf-photo analysis using generic object regions, OCR, and CLIP image embeddings.

The detector is still generic YOLO, not trained for retail packages. Product
matching uses CLIP only when real, owner-supplied reference images have been
embedded for the SKU; otherwise it falls back to OCR text similarity. Neither
method is a calibrated probability, and stock quantity always requires owner
physical confirmation.
"""
from __future__ import annotations

import math
import os
import re
from difflib import SequenceMatcher
from functools import lru_cache
from io import BytesIO
from typing import Any

from PIL import Image


EMBEDDING_DIMENSION = 512
DEFAULT_EMBEDDING_MODEL = "openai/clip-vit-base-patch32"


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
                "score_type": "ocr_text_similarity",
            })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:limit]


def _cosine_similarity(left: list[float], right: list[float]) -> float | None:
    """Cosine similarity for finite, non-zero vectors of equal dimensions."""
    if not left or len(left) != len(right):
        return None
    if not all(math.isfinite(float(value)) for value in left + right):
        return None
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm == 0 or right_norm == 0:
        return None
    score = sum(float(a) * float(b) for a, b in zip(left, right)) / (left_norm * right_norm)
    return max(-1.0, min(1.0, score))


def rank_visual_matches(
    query_embedding: list[float],
    catalogue: list[dict[str, Any]],
    limit: int = 3,
    threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Rank products by maximum cosine similarity to their real reference vectors.

    The score is a cosine similarity, not a calibrated confidence or probability.
    The initial threshold is a conservative operating default and must be
    calibrated against labelled store images before production use.
    """
    if len(query_embedding) != EMBEDDING_DIMENSION:
        raise ValueError(f"CLIP image embeddings must contain {EMBEDDING_DIMENSION} values")
    if limit < 1:
        raise ValueError("limit must be positive")
    if threshold is None:
        try:
            threshold = float(os.getenv("VISION_UNKNOWN_SIMILARITY_THRESHOLD", "0.58"))
        except ValueError:
            threshold = 0.58
    if not -1.0 <= threshold <= 1.0:
        raise ValueError("similarity threshold must be between -1 and 1")

    ranked: list[dict[str, Any]] = []
    for item in catalogue:
        references = item.get("reference_embeddings") or []
        scores = [
            _cosine_similarity(query_embedding, reference)
            for reference in references
            if isinstance(reference, list) and len(reference) == EMBEDDING_DIMENSION
        ]
        valid_scores = [score for score in scores if score is not None]
        if not valid_scores:
            continue
        score = max(valid_scores)
        if score >= threshold:
            ranked.append({
                "product_id": str(item.get("product_id", "")),
                "sku_code": str(item.get("sku_code", "")),
                "name": str(item.get("name", "")),
                "brand": str(item.get("brand", "")),
                "score": round(score, 6),
                "score_type": "cosine_similarity",
            })
    ranked.sort(key=lambda row: row["score"], reverse=True)
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


@lru_cache(maxsize=1)
def _clip_components():
    """Load the 512-dimensional CLIP model once per worker process."""
    from transformers import CLIPModel, CLIPProcessor

    model_name = os.getenv("VISION_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    processor = CLIPProcessor.from_pretrained(model_name)
    model = CLIPModel.from_pretrained(model_name)
    model.eval()
    return model, processor, model_name


def _embed_pil_image(image: Image.Image) -> tuple[list[float], str]:
    import torch

    model, processor, model_name = _clip_components()
    inputs = processor(images=image.convert("RGB"), return_tensors="pt")
    with torch.inference_mode():
        features = model.get_image_features(pixel_values=inputs["pixel_values"])
        if hasattr(features, "image_embeds"):
            features = features.image_embeds
        elif isinstance(features, (tuple, list)):
            features = features[0]
        features = torch.nn.functional.normalize(features, p=2, dim=-1)
    embedding = [float(value) for value in features[0].cpu().tolist()]
    if len(embedding) != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Configured image model returned {len(embedding)} dimensions; "
            f"the product_images schema requires {EMBEDDING_DIMENSION}"
        )
    return embedding, model_name


def embed_image_bytes(image_bytes: bytes) -> tuple[list[float], str]:
    """Create a normalized CLIP image embedding for a reference image."""
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    width, height = image.size
    if width < 64 or height < 64 or width * height > 25_000_000:
        raise ValueError("Image dimensions are outside supported limits")
    return _embed_pil_image(image)


def analyze_image(
    image_bytes: bytes,
    catalogue: list[dict[str, Any]],
    use_visual_embeddings: bool = False,
) -> dict[str, Any]:
    """Detect generic object regions and return crop vectors for pgvector lookup."""
    import numpy as np

    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    width, height = image.size
    if width < 64 or height < 64 or width * height > 25_000_000:
        raise ValueError("Image dimensions are outside supported limits")
    detector = _detector()
    reader = _ocr_reader()
    has_visual_references = bool(use_visual_embeddings)
    result = detector.predict(source=image, conf=0.25, verbose=False)[0]
    detections = []
    embedding_model = os.getenv("VISION_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    for box in result.boxes:
        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
        x1i, y1i = max(0, int(x1)), max(0, int(y1))
        x2i, y2i = min(width, int(x2)), min(height, int(y2))
        if x2i <= x1i or y2i <= y1i:
            continue
        crop = image.crop((x1i, y1i, x2i, y2i))
        texts = reader.readtext(np.asarray(crop), detail=0, paragraph=False)
        ocr_text = " ".join(str(t) for t in texts).strip()

        image_embedding = None
        if has_visual_references:
            image_embedding, embedding_model = _embed_pil_image(crop)
            matching_method = "clip_embedding_pending_pgvector"
        else:
            matching_method = "ocr_text_similarity"
        matches = match_catalogue(ocr_text, catalogue)

        class_id = int(box.cls[0].item())
        label = result.names.get(class_id, str(class_id))
        detection = {
            "bbox": [
                round(x1i / width, 5), round(y1i / height, 5),
                round(x2i / width, 5), round(y2i / height, 5),
            ],
            "detector_label": label,
            "detection_confidence": round(float(box.conf[0].item()), 4),
            "ocr_text": ocr_text,
            "top_matches": matches,
            "is_unknown": not bool(matches),
            "matching_method": matching_method,
            "quantity_requires_owner_confirmation": True,
        }
        if image_embedding is not None:
            # Internal API-to-API payload; the retail API consumes this vector
            # against PostgreSQL pgvector and removes it before returning JSON.
            detection["image_embedding"] = image_embedding
        detections.append(detection)
    return {
        "detector": os.getenv("VISION_DETECTOR_WEIGHTS", "yolo11n.pt"),
        "detections": detections,
        "detection_count": len(detections),
        "matching_method": "clip_embedding_pending_pgvector" if has_visual_references else "ocr_text_similarity",
        "embedding_model": embedding_model,
        "embedding_matching_enabled": has_visual_references,
        "stock_quantity_inferred": False,
        "owner_quantity_confirmation_required": True,
    }
