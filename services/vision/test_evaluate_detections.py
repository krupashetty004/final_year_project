import pytest

from evaluate_detections import evaluate_detections


def _sample(ground_truth, predictions):
    return {
        "image_id": "shelf-001",
        "ground_truth_boxes": ground_truth,
        "predicted_boxes": predictions,
    }


def _prediction(box, confidence=0.9):
    return {"bbox": box, "confidence": confidence, "label": "object"}


def test_perfect_region_prediction_has_perfect_metrics():
    box = [0.1, 0.1, 0.5, 0.8]
    report = evaluate_detections([_sample([box], [_prediction(box)])])
    metrics = report["metrics"]
    assert metrics["true_positive"] == 1
    assert metrics["false_positive"] == 0
    assert metrics["false_negative"] == 0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0
    assert report["region_average_precision_iou50"] == 1.0


def test_duplicate_proposals_are_not_counted_as_two_true_positives():
    box = [0.1, 0.1, 0.5, 0.8]
    report = evaluate_detections([
        _sample([box], [_prediction(box, 0.95), _prediction(box, 0.85)])
    ])
    metrics = report["metrics"]
    assert metrics["true_positive"] == 1
    assert metrics["false_positive"] == 1
    assert metrics["false_negative"] == 0
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 1.0


def test_low_iou_prediction_is_false_positive_and_ground_truth_is_missed():
    report = evaluate_detections([
        _sample(
            [[0.1, 0.1, 0.4, 0.4]],
            [_prediction([0.6, 0.6, 0.9, 0.9])],
        )
    ])
    metrics = report["metrics"]
    assert metrics["true_positive"] == 0
    assert metrics["false_positive"] == 1
    assert metrics["false_negative"] == 1
    assert report["region_average_precision_iou50"] == 0.0


def test_confidence_filter_excludes_low_confidence_proposals():
    box = [0.1, 0.1, 0.5, 0.8]
    report = evaluate_detections(
        [_sample([box], [_prediction(box, 0.2)])],
        confidence_threshold=0.25,
    )
    assert report["metrics"]["prediction_count"] == 0
    assert report["metrics"]["false_negative"] == 1


def test_region_evaluation_rejects_invalid_box_coordinates():
    with pytest.raises(ValueError, match="normalized coordinates"):
        evaluate_detections([
            _sample([[0.1, 0.1, 1.2, 0.4]], [])
        ])


def test_region_evaluation_rejects_duplicate_image_ids():
    sample = _sample([], [])
    duplicate = {**sample}
    with pytest.raises(ValueError, match="duplicate image_id"):
        evaluate_detections([sample, duplicate])
