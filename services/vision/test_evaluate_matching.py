import json

import pytest

from evaluate_matching import _load_jsonl, evaluate_samples


def _vector(*values):
    return list(values) + [0.0] * (512 - len(values))


def test_calibration_chooses_threshold_that_rejects_unknown_samples():
    samples = [
        {
            "query_id": "known-1",
            "expected_product_id": "sku-a",
            "query_embedding": _vector(1.0, 0.0),
            "catalogue": [
                {
                    "product_id": "sku-a",
                    "sku_code": "A",
                    "name": "Product A",
                    "brand": "Brand A",
                    "reference_embeddings": [_vector(0.99, 0.01)],
                },
                {
                    "product_id": "sku-b",
                    "sku_code": "B",
                    "name": "Product B",
                    "brand": "Brand B",
                    "reference_embeddings": [_vector(-1.0, 0.0)],
                },
            ],
        },
        {
            "query_id": "unknown-1",
            "expected_product_id": None,
            "query_embedding": _vector(0.0, 1.0),
            "catalogue": [
                {
                    "product_id": "sku-a",
                    "sku_code": "A",
                    "name": "Product A",
                    "brand": "Brand A",
                    "reference_embeddings": [_vector(1.0, 0.0)],
                },
            ],
        },
    ]
    report = evaluate_samples(samples, thresholds=[0.0, 0.58, 0.99, 1.0])
    assert report["calibration_status"] == "calibrated_on_supplied_labels"
    assert report["sample_count"] == 2
    assert report["known_top1_accuracy_before_threshold"] == 1.0
    assert report["recommended_threshold"] == 0.99
    assert report["recommended_threshold_metrics"]["balanced_known_unknown_accuracy"] == 1.0


def test_calibration_is_not_recommended_without_known_and_unknown_classes():
    samples = [{
        "query_id": "known-only",
        "expected_product_id": "sku-a",
        "query_embedding": _vector(1.0, 0.0),
        "catalogue": [{
            "product_id": "sku-a",
            "sku_code": "A",
            "name": "Product A",
            "brand": "Brand A",
            "reference_embeddings": [_vector(1.0, 0.0)],
        }],
    }]
    report = evaluate_samples(samples)
    assert report["calibration_status"] == "insufficient_label_classes"
    assert report["recommended_threshold"] is None


def test_wrong_top_sku_counts_as_error_not_a_correct_match():
    samples = [{
        "query_id": "wrong-top-1",
        "expected_product_id": "sku-b",
        "query_embedding": _vector(1.0, 0.0),
        "catalogue": [
            {
                "product_id": "sku-a",
                "sku_code": "A",
                "name": "Product A",
                "brand": "Brand A",
                "reference_embeddings": [_vector(1.0, 0.0)],
            },
            {
                "product_id": "sku-b",
                "sku_code": "B",
                "name": "Product B",
                "brand": "Brand B",
                "reference_embeddings": [_vector(0.0, 1.0)],
            },
        ],
    }]
    report = evaluate_samples(samples, thresholds=[0.5])
    assert report["known_top1_accuracy_before_threshold"] == 0.0
    assert report["configured_threshold_metrics"]["match_precision"] == 0.0
    assert report["configured_threshold_metrics"]["false_positive"] == 1
    assert report["configured_threshold_metrics"]["false_negative"] == 1


def test_loader_rejects_non_512_query_embedding(tmp_path):
    dataset = tmp_path / "labels.jsonl"
    dataset.write_text(json.dumps({
        "query_id": "bad",
        "expected_product_id": "sku-a",
        "query_embedding": [1.0, 0.0],
        "catalogue": [],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="512-dimensional"):
        _load_jsonl(dataset)


def test_loader_rejects_empty_dataset(tmp_path):
    dataset = tmp_path / "empty.jsonl"
    dataset.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no samples"):
        _load_jsonl(dataset)



def test_evaluation_reports_top3_recall_and_reciprocal_rank():
    samples = [{
        "query_id": "rank-two",
        "expected_product_id": "sku-b",
        "query_embedding": _vector(1.0, 0.0),
        "catalogue": [
            {
                "product_id": "sku-a",
                "sku_code": "A",
                "name": "Product A",
                "brand": "Brand A",
                "reference_embeddings": [_vector(1.0, 0.0)],
            },
            {
                "product_id": "sku-b",
                "sku_code": "B",
                "name": "Product B",
                "brand": "Brand B",
                "reference_embeddings": [_vector(0.8, 0.6)],
            },
            {
                "product_id": "sku-c",
                "sku_code": "C",
                "name": "Product C",
                "brand": "Brand C",
                "reference_embeddings": [_vector(-1.0, 0.0)],
            },
        ],
    }]
    report = evaluate_samples(samples, thresholds=[0.58])
    assert report["known_top1_accuracy_before_threshold"] == 0.0
    assert report["known_top3_recall_before_threshold"] == 1.0
    assert report["known_mean_reciprocal_rank_at_3"] == 0.5



def test_calibration_rejects_empty_or_invalid_threshold_sweep():
    sample = {
        "query_id": "known",
        "expected_product_id": "sku-a",
        "query_embedding": _vector(1.0, 0.0),
        "catalogue": [{
            "product_id": "sku-a",
            "sku_code": "A",
            "name": "Product A",
            "brand": "Brand A",
            "reference_embeddings": [_vector(1.0, 0.0)],
        }],
    }
    with pytest.raises(ValueError, match="At least one"):
        evaluate_samples([sample], thresholds=[])
    with pytest.raises(ValueError, match="finite cosine values"):
        evaluate_samples([sample], thresholds=[float("nan")])
    with pytest.raises(ValueError, match="finite cosine values"):
        evaluate_samples([sample], thresholds=[1.1])
