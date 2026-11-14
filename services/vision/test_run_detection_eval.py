from pathlib import Path

import pytest
from PIL import Image

from run_detection_eval import evaluate_detection_manifest, prepare_detection_samples


class Scalar:
    def __init__(self, value):
        self.value = value

    def item(self):
        return self.value


class CoordinateRow:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class Coordinates:
    def __init__(self, rows):
        self.rows = rows

    def __getitem__(self, index):
        return CoordinateRow(self.rows[index])


class FakeBox:
    def __init__(self, bbox, confidence=0.91, class_id=39):
        self.xyxy = Coordinates([bbox])
        self.conf = [Scalar(confidence)]
        self.cls = [Scalar(class_id)]


class FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes
        self.names = {39: "bottle"}


class FakeDetector:
    def __init__(self, boxes):
        self.boxes = boxes
        self.calls = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        return [FakeResult(self.boxes)]


def _write_image(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 100), "white").save(path, format="PNG")
    return path


def _manifest():
    return [{
        "image_id": "shelf-001",
        "image_path": "images/shelf-001.png",
        "ground_truth_boxes": [[0.1, 0.2, 0.8, 0.8]],
    }]


def test_run_detector_and_score_normalized_region_boxes(tmp_path):
    _write_image(tmp_path / "images" / "shelf-001.png")
    detector = FakeDetector([FakeBox([10, 20, 80, 80])])

    report = evaluate_detection_manifest(
        _manifest(),
        tmp_path,
        detector=detector,
        inference_confidence=0.001,
        score_confidence=0.25,
    )

    assert len(detector.calls) == 1
    assert detector.calls[0]["conf"] == 0.001
    assert report["evaluation_scope"] == "class_agnostic_object_region_localization"
    assert report["metrics"]["true_positive"] == 1
    assert report["metrics"]["f1"] == 1.0
    assert report["region_average_precision_iou50"] == 1.0


def test_run_detector_returns_empty_prediction_list_when_no_boxes(tmp_path):
    _write_image(tmp_path / "images" / "shelf-001.png")
    detector = FakeDetector([])
    rows = prepare_detection_samples(_manifest(), tmp_path, detector=detector)
    assert rows[0]["predicted_boxes"] == []


def test_detection_manifest_rejects_image_path_outside_dataset_root(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    rows = _manifest()
    rows[0]["image_path"] = "../outside.png"
    with pytest.raises(ValueError, match="stay inside the manifest directory"):
        prepare_detection_samples(rows, dataset, detector=FakeDetector([]))


def test_detection_manifest_rejects_duplicate_image_ids(tmp_path):
    _write_image(tmp_path / "images" / "shelf-001.png")
    rows = _manifest()
    rows.append(dict(rows[0]))
    with pytest.raises(ValueError, match="missing or duplicated"):
        prepare_detection_samples(rows, tmp_path, detector=FakeDetector([]))


def test_detection_manifest_rejects_invalid_images(tmp_path):
    image_path = tmp_path / "images" / "shelf-001.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="invalid image file"):
        prepare_detection_samples(_manifest(), tmp_path, detector=FakeDetector([]))
