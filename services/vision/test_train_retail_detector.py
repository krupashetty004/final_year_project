from pathlib import Path
from types import SimpleNamespace

import pytest

from train_retail_detector import train_detector, validate_training_options


def _dataset_yaml(path: Path):
    path.write_text(
        "path: ./retail_dataset\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: product_package\n",
        encoding="utf-8",
    )
    return path


def test_training_options_require_existing_dataset_yaml(tmp_path):
    dataset = _dataset_yaml(tmp_path / "dataset.yaml")
    assert validate_training_options(dataset, 50, 640, 16, 20) == dataset.resolve()
    with pytest.raises(FileNotFoundError):
        validate_training_options(tmp_path / "missing.yaml", 50, 640, 16, 20)


@pytest.mark.parametrize(
    ("epochs", "image_size", "batch_size", "patience"),
    [
        (0, 640, 16, 20),
        (1001, 640, 16, 20),
        (10, 32, 16, 20),
        (10, 640, 0, 20),
        (10, 640, 16, -1),
    ],
)
def test_training_options_reject_unsafe_ranges(tmp_path, epochs, image_size, batch_size, patience):
    dataset = _dataset_yaml(tmp_path / "dataset.yaml")
    with pytest.raises(ValueError):
        validate_training_options(dataset, epochs, image_size, batch_size, patience)


def test_training_requires_non_empty_dataset_configuration(tmp_path):
    dataset = tmp_path / "dataset.yaml"
    dataset.write_text("  \n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        validate_training_options(dataset, 50, 640, 16, 20)


def test_training_runner_saves_best_checkpoint_and_reports_validation(tmp_path):
    dataset = _dataset_yaml(tmp_path / "dataset.yaml")
    project = tmp_path / "runs"
    calls = []

    class FakeYolo:
        def __init__(self, weights):
            self.weights = weights

        def train(self, **kwargs):
            calls.append(("train", kwargs))
            save_dir = Path(kwargs["project"]) / kwargs["name"]
            weights_dir = save_dir / "weights"
            weights_dir.mkdir(parents=True)
            (weights_dir / "best.pt").write_bytes(b"fake-checkpoint")
            return SimpleNamespace(save_dir=str(save_dir))

        def val(self, **kwargs):
            calls.append(("val", kwargs))
            return SimpleNamespace(
                box=SimpleNamespace(mp=0.91, mr=0.88, map50=0.90, map=0.64)
            )

    report = train_detector(
        dataset_yaml=dataset,
        initial_weights="yolo11n.pt",
        project=project,
        run_name="test-run",
        epochs=5,
        image_size=320,
        batch_size=4,
        patience=2,
        yolo_factory=FakeYolo,
    )

    assert report["status"] == "trained_and_validated"
    assert report["task"] == "product_package_region_detection"
    assert Path(report["best_weights"]).is_file()
    assert report["validation_metrics"] == {
        "precision": 0.91,
        "recall": 0.88,
        "map50": 0.90,
        "map50_95": 0.64,
    }
    assert [call[0] for call in calls] == ["train", "val"]
    assert calls[1][1]["split"] == "val"
