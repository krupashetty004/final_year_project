"""Evaluate CLIP SKU retrieval and calibrate the unknown-item threshold.

Input is JSONL. Each row is one labelled query crop:
{
  "query_id": "shelf-001-region-01",
  "expected_product_id": "product-uuid-or-null",
  "query_embedding": [512 floats],
  "catalogue": [
    {
      "product_id": "product-uuid",
      "sku_code": "SKU-001",
      "name": "Example product",
      "brand": "Example",
      "reference_embeddings": [[512 floats], [512 floats]]
    }
  ]
}

Use expected_product_id=null for a genuinely unknown/unlisted product. The
utility reports retrieval metrics; it does not train a model or infer labels.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable

from pipeline import EMBEDDING_DIMENSION, rank_visual_matches


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"Line {line_number} must contain a JSON object")
            if len(item.get("query_embedding", [])) != EMBEDDING_DIMENSION:
                raise ValueError(f"Line {line_number}: query_embedding must be 512-dimensional")
            if not isinstance(item.get("catalogue"), list):
                raise ValueError(f"Line {line_number}: catalogue must be a list")
            expected = item.get("expected_product_id")
            if expected is not None and not isinstance(expected, str):
                raise ValueError(f"Line {line_number}: expected_product_id must be a string or null")
            if not item.get("query_id"):
                raise ValueError(f"Line {line_number}: query_id is required")
            rows.append(item)
    if not rows:
        raise ValueError("Evaluation file contains no samples")
    return rows


def _top_matches(query: list[float], catalogue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return rank_visual_matches(query, catalogue, limit=3, threshold=-1.0)


def _threshold_metrics(
    records: list[dict[str, Any]],
    threshold: float,
) -> dict[str, float | int | None]:
    true_positive = false_positive = false_negative = true_negative = 0
    known = unknown = 0
    top1_correct = 0
    for record in records:
        expected = record["expected_product_id"]
        predicted = record["top_product_id"]
        score = record["top_score"]
        accepted = predicted is not None and score is not None and score >= threshold
        if expected is None:
            unknown += 1
            if accepted:
                false_positive += 1
            else:
                true_negative += 1
        else:
            known += 1
            if predicted == expected:
                top1_correct += 1
            if accepted and predicted == expected:
                true_positive += 1
            else:
                false_negative += 1
                if accepted:
                    false_positive += 1

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    known_recall = true_positive / known if known else None
    unknown_rejection = true_negative / unknown if unknown else None
    balanced = (
        (known_recall + unknown_rejection) / 2
        if known_recall is not None and unknown_rejection is not None else None
    )
    return {
        "threshold": round(threshold, 6),
        "samples": len(records),
        "known_samples": known,
        "unknown_samples": unknown,
        "top1_accuracy_known": round(top1_correct / known, 6) if known else None,
        "match_precision": round(precision, 6),
        "match_recall_known": round(recall, 6),
        "match_f1": round(f1, 6),
        "unknown_rejection_recall": round(unknown_rejection, 6) if unknown_rejection is not None else None,
        "balanced_known_unknown_accuracy": round(balanced, 6) if balanced is not None else None,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
    }


def evaluate_samples(
    samples: Iterable[dict[str, Any]],
    thresholds: Iterable[float] | None = None,
) -> dict[str, Any]:
    """Compute per-query top-1 retrieval, threshold metrics and a calibrated cut-off."""
    prepared = []
    for index, sample in enumerate(samples, start=1):
        query = [float(value) for value in sample["query_embedding"]]
        if not all(math.isfinite(value) for value in query):
            raise ValueError(f"Sample {index}: query embedding contains non-finite values")
        matches = _top_matches(query, sample["catalogue"])
        prepared.append({
            "query_id": str(sample["query_id"]),
            "expected_product_id": sample.get("expected_product_id"),
            "top_product_id": matches[0]["product_id"] if matches else None,
            "top_score": float(matches[0]["score"]) if matches else None,
            "top3_product_ids": [match["product_id"] for match in matches],
        })

    known_count = sum(row["expected_product_id"] is not None for row in prepared)
    unknown_count = len(prepared) - known_count
    if thresholds is None:
        scores = [row["top_score"] for row in prepared if row["top_score"] is not None]
        thresholds = sorted({0.0, 1.0, *(round(score, 4) for score in scores)})
    candidate_metrics = [_threshold_metrics(prepared, float(value)) for value in thresholds]

    best = None
    calibration_status = "insufficient_label_classes"
    if known_count > 0 and unknown_count > 0:
        best = max(
            candidate_metrics,
            key=lambda row: (
                float(row["balanced_known_unknown_accuracy"] or 0),
                float(row["match_f1"]),
                float(row["threshold"]),
            ),
        )
        calibration_status = "calibrated_on_supplied_labels"

    baseline = _threshold_metrics(prepared, 0.58)
    known_rows = [row for row in prepared if row["expected_product_id"] is not None]
    rank_correct = sum(
        row["top_product_id"] == row["expected_product_id"]
        for row in known_rows
    )
    top3_correct = sum(
        row["expected_product_id"] in row["top3_product_ids"]
        for row in known_rows
    )
    reciprocal_ranks = []
    for row in known_rows:
        try:
            rank = row["top3_product_ids"].index(row["expected_product_id"]) + 1
            reciprocal_ranks.append(1.0 / rank)
        except ValueError:
            reciprocal_ranks.append(0.0)
    return {
        "status": "evaluated",
        "calibration_status": calibration_status,
        "sample_count": len(prepared),
        "known_sample_count": known_count,
        "unknown_sample_count": unknown_count,
        "known_top1_accuracy_before_threshold": (
            round(rank_correct / known_count, 6) if known_count else None
        ),
        "known_top3_recall_before_threshold": (
            round(top3_correct / known_count, 6) if known_count else None
        ),
        "known_mean_reciprocal_rank_at_3": (
            round(sum(reciprocal_ranks) / known_count, 6) if known_count else None
        ),
        "configured_threshold_metrics": baseline,
        "recommended_threshold": best["threshold"] if best is not None else None,
        "recommended_threshold_metrics": best,
        "threshold_sweep": candidate_metrics,
        "notes": [
            "Cosine similarity is a ranking score, not a probability.",
            "Threshold metrics are valid only for the supplied labelled sample distribution.",
            "Keep a separate held-out test set; do not report calibration-set metrics as final test accuracy.",
            "Use representative store images, varied lighting and packaging views, and genuinely unknown products.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Labelled query-embedding JSONL file")
    parser.add_argument("--output", type=Path, help="Optional JSON report output path")
    args = parser.parse_args()
    report = evaluate_samples(_load_jsonl(args.dataset))
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
