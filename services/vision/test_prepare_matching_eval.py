import json

import pytest

import prepare_matching_eval as prepare


def _write(path, payload=b"image"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _manifest(query_path="query.jpg", reference_path="reference.jpg"):
    return [{
        "query_id": "query-1",
        "query_image": query_path,
        "expected_product_id": "sku-1",
        "catalogue": [{
            "product_id": "sku-1",
            "sku_code": "SKU-1",
            "name": "Test product",
            "brand": "Test brand",
            "reference_images": [reference_path],
        }],
    }]


def test_prepare_manifest_creates_query_and_reference_embeddings(tmp_path, monkeypatch):
    query = _write(tmp_path / "query.jpg", b"query")
    reference = _write(tmp_path / "reference.jpg", b"reference")
    calls = []

    def fake_embed(raw):
        calls.append(raw)
        vector = [1.0] + [0.0] * 511 if raw == b"query" else [0.0, 1.0] + [0.0] * 510
        return vector, "openai/clip-vit-base-patch32"

    monkeypatch.setattr(prepare, "embed_image_bytes", fake_embed)
    result = prepare.prepare_matching_samples(_manifest(), tmp_path)

    assert result[0]["query_embedding"][0] == 1.0
    assert result[0]["catalogue"][0]["reference_embeddings"][0][1] == 1.0
    assert result[0]["embedding_model"] == "openai/clip-vit-base-patch32"
    assert len(calls) == 2


def test_prepare_manifest_caches_reused_reference_images(tmp_path, monkeypatch):
    _write(tmp_path / "query-1.jpg", b"query-1")
    _write(tmp_path / "query-2.jpg", b"query-2")
    _write(tmp_path / "reference.jpg", b"reference")
    calls = []

    def fake_embed(raw):
        calls.append(raw)
        return [1.0] + [0.0] * 511, "openai/clip-vit-base-patch32"

    monkeypatch.setattr(prepare, "embed_image_bytes", fake_embed)
    rows = _manifest()
    rows.append({
        **rows[0],
        "query_id": "query-2",
        "query_image": "query-2.jpg",
    })
    result = prepare.prepare_matching_samples(rows, tmp_path)

    assert len(result) == 2
    assert calls.count(b"reference") == 1
    assert len(calls) == 3


def test_prepare_manifest_rejects_query_reference_image_leakage(tmp_path, monkeypatch):
    _write(tmp_path / "same.jpg", b"same")
    monkeypatch.setattr(
        prepare,
        "embed_image_bytes",
        lambda _raw: ([1.0] + [0.0] * 511, "clip"),
    )
    with pytest.raises(ValueError, match="cannot also be a reference"):
        prepare.prepare_matching_samples(_manifest("same.jpg", "same.jpg"), tmp_path)


def test_prepare_manifest_requires_reference_images(tmp_path, monkeypatch):
    _write(tmp_path / "query.jpg")
    monkeypatch.setattr(
        prepare,
        "embed_image_bytes",
        lambda _raw: ([1.0] + [0.0] * 511, "clip"),
    )
    rows = _manifest()
    rows[0]["catalogue"][0]["reference_images"] = []
    with pytest.raises(ValueError, match="at least one reference"):
        prepare.prepare_matching_samples(rows, tmp_path)


def test_prepare_manifest_rejects_duplicate_query_ids(tmp_path, monkeypatch):
    _write(tmp_path / "query.jpg")
    _write(tmp_path / "query-2.jpg")
    _write(tmp_path / "reference.jpg")
    monkeypatch.setattr(
        prepare,
        "embed_image_bytes",
        lambda _raw: ([1.0] + [0.0] * 511, "clip"),
    )
    rows = _manifest()
    rows.append({**rows[0], "query_image": "query-2.jpg"})
    with pytest.raises(ValueError, match="duplicated"):
        prepare.prepare_matching_samples(rows, tmp_path)


def test_prepare_manifest_rejects_wrong_embedding_dimension(tmp_path, monkeypatch):
    _write(tmp_path / "query.jpg")
    _write(tmp_path / "reference.jpg")
    monkeypatch.setattr(prepare, "embed_image_bytes", lambda _raw: ([1.0], "clip"))
    with pytest.raises(ValueError, match="512 values"):
        prepare.prepare_matching_samples(_manifest(), tmp_path)


def test_manifest_loader_requires_non_empty_jsonl(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no samples"):
        prepare._load_manifest(path)
