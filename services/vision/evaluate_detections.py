"""Evaluate class-agnostic shelf-object region proposals against labelled boxes.

JSONL sample format:
{
  "image_id": "shelf-photo-001",
  "ground_truth_boxes": [[0.10, 0.12, 0.42, 0.82]],
  "predicted_boxes": [
    {"bbox": [0.11, 0.13, 0.41, 0.81], "confidence": 0.91, "label": "bottle"}
  ]
}

Boxes are normalized [x1, y1, x2, y2] coordinates in the 0..1 image range.
This evaluator measures candidate-region localization only. It does not measure
SKU identity, class correctness, or inventory quantity estimation.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable


def _validate_box(box: Any, context: str) -> list[float]:
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise ValueError(f"{context}: box must contain four normalized coordinates")
    values = [float(value) for value in box]
    if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values):
        raise ValueError(f"{context}: box coordinates must be finite and in [0, 1]")
    if values[2] <= values[0] or values[3] <= values[1]:
        raise ValueError(f"{context}: box must have positive width and height")
    return values


def _intersection_over_union(left: list[float], right: list[float]) -> float:
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def _prepare_samples(samples: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    seen_ids = set()
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, dict) or not sample.get("image_id"):
            raise ValueError(f"Sample {index}: image_id is required")
        image_id = str(sample["image_id"])
        if image_id in seen_ids:
            raise ValueError(f"Sample {index}: duplicate image_id {image_id!r}")
        seen_ids.add(image_id)
        gt = sample.get("ground_truth_boxes")
        preds = sample.get("predicted_boxes")
        if not isinstance(gt, list) or not isinstance(preds, list):
            raise ValueError(f"Sample {index}: ground_truth_boxes and predicted_boxes must be lists")
        gt_boxes = [
            _validate_box(box, f"Sample {index} ground-truth box {box_index}")
            for box_index, box in enumerate(gt, start=1)
        ]
        predicted = []
        for prediction_index, prediction in enumerate(preds, start=1):
            if not isinstance(prediction, dict):
                raise ValueError(f"Sample {index} prediction {prediction_index} must be an object")
            bbox = _validate_box(
                prediction.get("bbox"),
                f"Sample {index} prediction {prediction_index}",
            )
            confidence = float(prediction.get("confidence"))
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise ValueError(f"Sample {index} prediction {prediction_index}: confidence must be in [0, 1]")
            predicted.append({
                "bbox": bbox,
                "confidence": confidence,
                "label": str(prediction.get("label") or "object"),
            })
        prepared.append({
            "image_id": image_id,
            "ground_truth_boxes": gt_boxes,
            "predicted_boxes": predicted,
        })
    if not prepared:
        raise ValueError("Evaluation file contains no image samples")
    return prepared


def _match_at_confidence(
    samples: list[dict[str, Any]],
    confidence_threshold: float,
    iou_threshold: float,
) -> dict[str, Any]:
    true_positive = false_positive = false_negative = 0
    total_gt = sum(len(sample["ground_truth_boxes"]) for sample in samples)
    total_predictions = 0
    for sample in samples:
        ground_truth = sample["ground_truth_boxes"]
        matched = set()
        predictions = sorted(
            (p for p in sample["predicted_boxes"] if p["confidence"] >= confidence_threshold),
            key=lambda row: row["confidence"],
            reverse=True,
        )
        total_predictions += len(predictions)
        for prediction in predictions:
            candidates = [
                (_intersection_over_union(prediction["bbox"], box), gt_index)
                for gt_index, box in enumerate(ground_truth)
                if gt_index not in matched
            ]
            best_iou, best_index = max(candidates, default=(0.0, -1))
            if best_index >= 0 and best_iou >= iou_threshold:
                true_positive += 1
                matched.add(best_index)
            else:
                false_positive += 1
        false_negative += len(ground_truth) - len(matched)

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / total_gt if total_gt else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "confidence_threshold": round(confidence_threshold, 4),
        "iou_threshold": round(iou_threshold, 4),
        "image_count": len(samples),
        "ground_truth_box_count": total_gt,
        "prediction_count": total_predictions,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _average_precision_50(samples: list[dict[str, Any]]) -> float | None:
    total_gt = sum(len(sample["ground_truth_boxes"]) for sample in samples)
    if total_gt == 0:
        return None
    predictions = []
    boxes_by_image = {}
    for sample in samples:
        boxes_by_image[sample["image_id"]] = sample["ground_truth_boxes"]
        for prediction in sample["predicted_boxes"]:
            predictions.append({
                "image_id": sample["image_id"],
                **prediction,
            })
    predictions.sort(key=lambda row: row["confidence"], reverse=True)
    matched_by_image = {sample["image_id"]: set() for sample in samples}
    cumulative_tp = 0
    cumulative_fp = 0
    precision_recall = []
    for prediction in predictions:
        image_id = prediction["image_id"]
        gt_boxes = boxes_by_image[image_id]
        matched = matched_by_image[image_id]
        candidates = [
            (_intersection_over_union(prediction["bbox"], box), gt_index)
            for gt_index, box in enumerate(gt_boxes)
            if gt_index not in matched
        ]
        best_iou, best_index = max(candidates, default=(0.0, -1))
        if best_index >= 0 and best_iou >= 0.5:
            cumulative_tp += 1
            matched.add(best_index)
        else:
            cumulative_fp += 1
        recall = cumulative_tp / total_gt
        precision = cumulative_tp / (cumulative_tp + cumulative_fp)
        precision_recall.append((recall, precision))

    interpolated = []
    for step in range(101):
        recall_level = step / 100
        eligible_precision = [
            precision
            for recall, precision in precision_recall
            if recall >= recall_level
        ]
        interpolated.append(max(eligible_precision, default=0.0))
    return round(sum(interpolated) / len(interpolated), 6)


def evaluate_detections(
    samples: Iterable[dict[str, Any]],
    confidence_threshold: float = 0.25,
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    if not 0.0 <= confidence_threshold <= 1.0:
        raise ValueError("confidence_threshold must be in [0, 1]")
    if not 0.0 < iou_threshold <= 1.0:
        raise ValueError("iou_threshold must be in (0, 1]")
    prepared = _prepare_samples(samples)
    metrics = _match_at_confidence(prepared, confidence_threshold, iou_threshold)
    return {
        "status": "evaluated",
        "evaluation_scope": "class_agnostic_object_region_localization",
        "metrics": metrics,
        "region_average_precision_iou50": _average_precision_50(prepared),
        "notes": [
            "This measures region localization only, not SKU identity or quantity counting.",
            "Use real labelled shelf images from different stores, product sizes, angles and lighting.",
            "Keep a separate held-out test set; do not use the same images for tuning and final reporting.",
            "AP@0.50 is class-agnostic and must not be presented as retail SKU mAP.",
        ],
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Labelled shelf-box JSONL file")
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate_detections(
        _load_jsonl(args.dataset),
        confidence_threshold=args.confidence,
        iou_threshold=args.iou,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
