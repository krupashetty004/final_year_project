"""Run the generic YOLO detector on labelled shelf photos and score its regions.

Input JSONL row:
{
  "image_id": "shelf-001",
  "image_path": "images/shelf-001.jpg",
  "ground_truth_boxes": [[0.10, 0.12, 0.42, 0.82]]
}

Coordinates are normalized [x1, y1, x2, y2]. This is a class-agnostic object
region evaluation only; it does not measure SKU identity or inventory counts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image

from evaluate_detections import evaluate_detections
from pipeline import _detector

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    samples = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on manifest line {line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Manifest line {line_number} must be a JSON object")
            samples.append(row)
    if not samples:
        raise ValueError("Detection manifest contains no image samples")
    return samples


def prepare_detection_samples(
    manifest_rows: list[dict[str, Any]],
    manifest_directory: Path,
    detector: Any | None = None,
    inference_confidence: float = 0.001,
) -> list[dict[str, Any]]:
    """Run YOLO and return evaluator-compatible boxes for every labelled image."""
    if not 0.0 <= inference_confidence <= 1.0:
        raise ValueError("inference_confidence must be in [0, 1]")
    manifest_root = manifest_directory.resolve()
    model = detector or _detector()
    seen_ids: set[str] = set()
    prepared = []

    for index, sample in enumerate(manifest_rows, start=1):
        context = f"Manifest sample {index}"
        if not isinstance(sample, dict):
            raise ValueError(f"{context} must be an object")
        image_id = str(sample.get("image_id") or "").strip()
        if not image_id or image_id in seen_ids:
            raise ValueError(f"{context}: image_id is missing or duplicated")
        seen_ids.add(image_id)
        ground_truth = sample.get("ground_truth_boxes")
        if not isinstance(ground_truth, list):
            raise ValueError(f"{context}: ground_truth_boxes must be a list")
        image_path_value = sample.get("image_path")
        if not isinstance(image_path_value, str) or not image_path_value.strip():
            raise ValueError(f"{context}: image_path is required")
        image_path = (manifest_root / image_path_value).resolve()
        try:
            image_path.relative_to(manifest_root)
        except ValueError as exc:
            raise ValueError(f"{context}: image_path must stay inside the manifest directory") from exc
        try:
            raw = image_path.read_bytes()
        except OSError as exc:
            raise ValueError(f"{context}: cannot read image {image_path}: {exc}") from exc
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError(f"{context}: image must be non-empty and no larger than 10 MB")
        try:
            from io import BytesIO

            image = Image.open(BytesIO(raw)).convert("RGB")
        except Exception as exc:
            raise ValueError(f"{context}: invalid image file: {exc}") from exc
        width, height = image.size
        if width < 64 or height < 64 or width * height > MAX_IMAGE_PIXELS:
            raise ValueError(f"{context}: image dimensions are outside supported limits")

        result = model.predict(
            source=image,
            conf=inference_confidence,
            verbose=False,
        )[0]
        predictions = []
        boxes = getattr(result, "boxes", None)
        names = getattr(result, "names", {})
        if boxes is not None:
            for box in boxes:
                x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
                x1 = min(1.0, max(0.0, x1 / width))
                y1 = min(1.0, max(0.0, y1 / height))
                x2 = min(1.0, max(0.0, x2 / width))
                y2 = min(1.0, max(0.0, y2 / height))
                if x2 <= x1 or y2 <= y1:
                    continue
                class_id = int(box.cls[0].item())
                predictions.append({
                    "bbox": [round(x1, 6), round(y1, 6), round(x2, 6), round(y2, 6)],
                    "confidence": round(float(box.conf[0].item()), 6),
                    "label": str(names.get(class_id, class_id)) if isinstance(names, dict) else str(class_id),
                })
        prepared.append({
            "image_id": image_id,
            "ground_truth_boxes": ground_truth,
            "predicted_boxes": predictions,
        })
    return prepared


def evaluate_detection_manifest(
    manifest_rows: list[dict[str, Any]],
    manifest_directory: Path,
    detector: Any | None = None,
    inference_confidence: float = 0.001,
    score_confidence: float = 0.25,
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    samples = prepare_detection_samples(
        manifest_rows,
        manifest_directory,
        detector=detector,
        inference_confidence=inference_confidence,
    )
    report = evaluate_detections(
        samples,
        confidence_threshold=score_confidence,
        iou_threshold=iou_threshold,
    )
    report["detector_weights"] = os.getenv("VISION_DETECTOR_WEIGHTS", "yolo11n.pt")
    report["inference_confidence"] = inference_confidence
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Labelled shelf image JSONL manifest")
    parser.add_argument("--weights", default=os.getenv("VISION_DETECTOR_WEIGHTS", "yolo11n.pt"))
    parser.add_argument("--inference-confidence", type=float, default=0.001)
    parser.add_argument("--score-confidence", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True, help="JSON metrics report output")
    args = parser.parse_args()

    os.environ["VISION_DETECTOR_WEIGHTS"] = args.weights
    _detector.cache_clear()
    manifest_path = args.manifest.resolve()
    rows = _load_manifest(manifest_path)
    report = evaluate_detection_manifest(
        rows,
        manifest_path.parent,
        inference_confidence=args.inference_confidence,
        score_confidence=args.score_confidence,
        iou_threshold=args.iou,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
