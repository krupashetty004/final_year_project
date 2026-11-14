"""Fine-tune YOLO for product-package regions; CLIP remains responsible for SKU matching.

Dataset YAML must use distinct train/val images and YOLO-format labels. Prefer
splitting by original photo/session and store to prevent near-duplicate leakage.
This command never invents annotations and never replaces the deployed weights.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Callable


def validate_training_options(
    dataset_yaml: Path,
    epochs: int,
    image_size: int,
    batch_size: int,
    patience: int,
) -> Path:
    dataset = dataset_yaml.resolve()
    if not dataset.is_file():
        raise FileNotFoundError(f"Dataset YAML not found: {dataset}")
    if dataset.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("Dataset configuration must be a .yaml or .yml file")
    if not dataset.read_text(encoding="utf-8").strip():
        raise ValueError("Dataset YAML is empty")
    if epochs < 1 or epochs > 1000:
        raise ValueError("epochs must be between 1 and 1000")
    if image_size < 64 or image_size > 2048:
        raise ValueError("image_size must be between 64 and 2048")
    if batch_size < 1 or batch_size > 256:
        raise ValueError("batch_size must be between 1 and 256")
    if patience < 0 or patience > 200:
        raise ValueError("patience must be between 0 and 200")
    return dataset


def _metric_value(metrics: Any, name: str) -> float | None:
    value = getattr(metrics, name, None)
    return float(value) if value is not None else None


def train_detector(
    dataset_yaml: Path,
    initial_weights: str,
    project: Path,
    run_name: str,
    epochs: int = 100,
    image_size: int = 640,
    batch_size: int = 16,
    patience: int = 20,
    device: str | None = None,
    seed: int = 42,
    yolo_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Train a package-region detector and evaluate the best checkpoint on val."""
    dataset = validate_training_options(
        dataset_yaml,
        epochs,
        image_size,
        batch_size,
        patience,
    )
    if not initial_weights.strip():
        raise ValueError("initial_weights must not be empty")
    if not run_name.strip():
        raise ValueError("run_name must not be empty")
    if yolo_factory is None:
        from ultralytics import YOLO

        yolo_factory = YOLO

    model = yolo_factory(initial_weights)
    train_kwargs = {
        "data": str(dataset),
        "epochs": epochs,
        "imgsz": image_size,
        "batch": batch_size,
        "patience": patience,
        "project": str(project),
        "name": run_name,
        "seed": seed,
        "deterministic": True,
        "plots": True,
        "verbose": True,
    }
    if device:
        train_kwargs["device"] = device
    train_result = model.train(**train_kwargs)
    trainer = getattr(model, "trainer", None)
    save_dir_value = (
        getattr(trainer, "save_dir", None)
        or getattr(train_result, "save_dir", None)
        or (project / run_name)
    )
    save_dir = Path(save_dir_value)
    best_weights = save_dir / "weights" / "best.pt"
    if not best_weights.is_file():
        raise FileNotFoundError(
            f"Training completed without a best.pt checkpoint at {best_weights}"
        )

    best_model = yolo_factory(str(best_weights))
    validation = best_model.val(
        data=str(dataset),
        split="val",
        imgsz=image_size,
        batch=batch_size,
        plots=True,
        verbose=True,
        **({"device": device} if device else {}),
    )
    box_metrics = getattr(validation, "box", None)
    if box_metrics is None:
        raise RuntimeError("YOLO validation returned no bounding-box metrics")

    return {
        "status": "trained_and_validated",
        "task": "product_package_region_detection",
        "sku_matching_method": "CLIP reference-image retrieval remains a separate pipeline stage",
        "initial_weights": initial_weights,
        "best_weights": str(best_weights.resolve()),
        "dataset_yaml": str(dataset),
        "epochs_requested": epochs,
        "image_size": image_size,
        "batch_size": batch_size,
        "validation_split": "val",
        "validation_metrics": {
            "precision": _metric_value(box_metrics, "mp"),
            "recall": _metric_value(box_metrics, "mr"),
            "map50": _metric_value(box_metrics, "map50"),
            "map50_95": _metric_value(box_metrics, "map"),
        },
        "notes": [
            "Metrics are from the supplied validation split, not a separate held-out test set.",
            "Use separate stores/photos for training, validation and final test to reduce leakage.",
            "This package-region detector does not identify SKUs or estimate hidden/stacked quantities.",
            "The best checkpoint is saved as an artifact; it is not activated or deployed automatically.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="YOLO dataset YAML with train/val splits")
    parser.add_argument("--weights", default=os.getenv("VISION_DETECTOR_WEIGHTS", "yolo11n.pt"))
    parser.add_argument("--project", type=Path, default=Path("runs/retail_detector"))
    parser.add_argument("--name", default="package-regions")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--device", default=None, help="Optional Ultralytics device, e.g. 0 or cpu")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--report", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    report = train_detector(
        dataset_yaml=args.data,
        initial_weights=args.weights,
        project=args.project,
        run_name=args.name,
        epochs=args.epochs,
        image_size=args.imgsz,
        batch_size=args.batch,
        patience=args.patience,
        device=args.device,
        seed=args.seed,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    report_path = args.report or (Path(report["best_weights"]).parent.parent / "training_metrics.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
