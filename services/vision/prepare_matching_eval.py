"""Prepare a labelled real-image manifest for evaluate_matching.py.

Manifest JSONL row:
{
  "query_id": "shelf-01-box-01",
  "query_image": "queries/query-01.jpg",
  "expected_product_id": "product-uuid-or-null",
  "catalogue": [
    {
      "product_id": "product-uuid",
      "sku_code": "SKU-001",
      "name": "Example product",
      "brand": "Example brand",
      "reference_images": ["references/sku-001-front.jpg", "references/sku-001-back.jpg"]
    }
  ]
}

All image paths are relative to the manifest file. The same exact image file
cannot be used as both a query and a reference within one evaluation sample.
Split by original photo/session/store before building calibration and held-out
test manifests to avoid leakage from visually near-identical crops.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pipeline import DEFAULT_EMBEDDING_MODEL, embed_image_bytes

MAX_IMAGE_BYTES = 10 * 1024 * 1024


def _read_image(path: Path) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"Cannot read image {path}: {exc}") from exc
    if not raw:
        raise ValueError(f"Image is empty: {path}")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image exceeds 10 MB: {path}")
    return raw


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on manifest line {line_number}: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"Manifest line {line_number} must be a JSON object")
            rows.append(item)
    if not rows:
        raise ValueError("Manifest contains no samples")
    return rows


def prepare_matching_samples(
    manifest_rows: list[dict[str, Any]],
    manifest_directory: Path,
) -> list[dict[str, Any]]:
    """Embed query crops and reference images, caching repeated reference files."""
    cache: dict[Path, tuple[list[float], str]] = {}

    def embed_relative(raw_path: Any, context: str) -> tuple[list[float], str, Path]:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"{context}: image path is required")
        resolved = (manifest_directory / raw_path).resolve()
        if resolved in cache:
            vector, model_name = cache[resolved]
        else:
            vector, model_name = embed_image_bytes(_read_image(resolved))
            cache[resolved] = (vector, model_name)
        if len(vector) != 512:
            raise ValueError(f"{context}: embedding model must return 512 values")
        return vector, model_name, resolved

    prepared = []
    seen_query_ids: set[str] = set()
    for index, sample in enumerate(manifest_rows, start=1):
        context = f"Manifest sample {index}"
        if not isinstance(sample, dict):
            raise ValueError(f"{context} must be an object")
        query_id = str(sample.get("query_id") or "").strip()
        if not query_id or query_id in seen_query_ids:
            raise ValueError(f"{context}: query_id is missing or duplicated")
        seen_query_ids.add(query_id)
        expected = sample.get("expected_product_id")
        if expected is not None and not isinstance(expected, str):
            raise ValueError(f"{context}: expected_product_id must be a string or null")
        catalogue = sample.get("catalogue")
        if not isinstance(catalogue, list) or not catalogue:
            raise ValueError(f"{context}: catalogue must be a non-empty list")

        query_vector, model_name, query_path = embed_relative(
            sample.get("query_image"),
            f"{context} query_image",
        )
        prepared_catalogue = []
        reference_paths: set[Path] = set()
        for product_index, product in enumerate(catalogue, start=1):
            product_context = f"{context} catalogue product {product_index}"
            if not isinstance(product, dict):
                raise ValueError(f"{product_context} must be an object")
            product_id = str(product.get("product_id") or "").strip()
            sku_code = str(product.get("sku_code") or "").strip()
            reference_images = product.get("reference_images")
            if not product_id or not sku_code:
                raise ValueError(f"{product_context} requires product_id and sku_code")
            if not isinstance(reference_images, list) or not reference_images:
                raise ValueError(f"{product_context} requires at least one reference image")
            reference_embeddings = []
            for reference_index, image_path in enumerate(reference_images, start=1):
                vector, reference_model, resolved = embed_relative(
                    image_path,
                    f"{product_context} reference image {reference_index}",
                )
                if resolved == query_path:
                    raise ValueError(
                        f"{context}: query image cannot also be a reference image"
                    )
                if reference_model != model_name:
                    raise ValueError("All reference and query embeddings must use the same model")
                reference_paths.add(resolved)
                reference_embeddings.append(vector)
            prepared_catalogue.append({
                "product_id": product_id,
                "sku_code": sku_code,
                "name": str(product.get("name") or ""),
                "brand": str(product.get("brand") or ""),
                "reference_embeddings": reference_embeddings,
            })

        prepared.append({
            "query_id": query_id,
            "expected_product_id": expected,
            "query_embedding": query_vector,
            "catalogue": prepared_catalogue,
            "embedding_model": model_name,
        })
    return prepared


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Labelled image manifest JSONL file")
    parser.add_argument("--output", type=Path, required=True, help="Prepared embedding JSONL output")
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    samples = prepare_matching_samples(_load_manifest(manifest), manifest.parent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        for sample in samples:
            stream.write(json.dumps(sample, ensure_ascii=False) + "\\n")
    print(json.dumps({
        "prepared_samples": len(samples),
        "output": str(args.output),
        "embedding_model": samples[0]["embedding_model"] if samples else DEFAULT_EMBEDDING_MODEL,
        "note": "Use a separate held-out manifest from distinct photos/sessions for final evaluation.",
    }, indent=2))


if __name__ == "__main__":
    main()
