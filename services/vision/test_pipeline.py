from pipeline import match_catalogue


def test_ocr_matching_ranks_correct_sku_first():
    catalogue = [
        {"product_id": "1", "sku_code": "SKU-001", "name": "Tata Salt 1kg", "brand": "Tata"},
        {"product_id": "2", "sku_code": "SKU-002", "name": "Aashirvaad Atta 5kg", "brand": "Aashirvaad"},
    ]
    matches = match_catalogue("TATA SALT 1 KG", catalogue)
    assert matches
    assert matches[0]["product_id"] == "1"


def test_unreadable_or_unrelated_ocr_does_not_force_sku_match():
    catalogue = [
        {"product_id": "1", "sku_code": "SKU-001", "name": "Tata Salt 1kg", "brand": "Tata"},
    ]
    assert match_catalogue("", catalogue) == []
    assert match_catalogue("unrelated xyz", catalogue) == []
