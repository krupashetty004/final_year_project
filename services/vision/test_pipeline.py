from pipeline import match_catalogue, rank_visual_matches


def test_ocr_matching_ranks_correct_sku_first():
    catalogue = [
        {"product_id": "1", "sku_code": "SKU-001", "name": "Tata Salt 1kg", "brand": "Tata"},
        {"product_id": "2", "sku_code": "SKU-002", "name": "Aashirvaad Atta 5kg", "brand": "Aashirvaad"},
    ]
    matches = match_catalogue("TATA SALT 1 KG", catalogue)
    assert matches
    assert matches[0]["product_id"] == "1"
    assert matches[0]["score_type"] == "ocr_text_similarity"


def test_unreadable_or_unrelated_ocr_does_not_force_sku_match():
    catalogue = [
        {"product_id": "1", "sku_code": "SKU-001", "name": "Tata Salt 1kg", "brand": "Tata"},
    ]
    assert match_catalogue("", catalogue) == []
    assert match_catalogue("unrelated xyz", catalogue) == []


def test_clip_visual_matching_ranks_most_similar_reference():
    query = [1.0] + [0.0] * 511
    near = [0.8, 0.6] + [0.0] * 510
    far = [-1.0] + [0.0] * 511
    catalogue = [
        {
            "product_id": "wrong", "sku_code": "SKU-002", "name": "Other Item",
            "brand": "Other", "reference_embeddings": [far],
        },
        {
            "product_id": "right", "sku_code": "SKU-001", "name": "Target Item",
            "brand": "Target", "reference_embeddings": [near, query],
        },
    ]
    matches = rank_visual_matches(query, catalogue, threshold=0.58)
    assert len(matches) == 1
    assert matches[0]["product_id"] == "right"
    assert matches[0]["score"] == 1.0
    assert matches[0]["score_type"] == "cosine_similarity"


def test_visual_matching_fails_closed_below_similarity_threshold():
    query = [1.0] + [0.0] * 511
    reference = [0.0, 1.0] + [0.0] * 510
    catalogue = [{
        "product_id": "1", "sku_code": "SKU-001", "name": "Unrelated",
        "brand": "Brand", "reference_embeddings": [reference],
    }]
    assert rank_visual_matches(query, catalogue, threshold=0.58) == []


def test_visual_matching_ignores_placeholder_rows_without_embeddings():
    query = [1.0] + [0.0] * 511
    catalogue = [{
        "product_id": "1", "sku_code": "SKU-001", "name": "Placeholder",
        "brand": "Brand", "reference_embeddings": [],
    }]
    assert rank_visual_matches(query, catalogue, threshold=0.58) == []


def test_visual_matching_rejects_wrong_embedding_dimension():
    try:
        rank_visual_matches([1.0, 0.0], [], threshold=0.5)
    except ValueError as exc:
        assert "512" in str(exc)
    else:
        raise AssertionError("Expected a 512-dimensional embedding validation error")
