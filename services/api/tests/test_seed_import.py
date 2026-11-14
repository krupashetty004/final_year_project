from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from scripts.import_sqlite_seed import convert_value


def test_empty_text_is_preserved_for_non_nullable_catalogue_fields():
    assert convert_value("", String(120)) == ""


def test_empty_non_text_value_becomes_none():
    assert convert_value("", Numeric(12, 3)) is None


def test_numeric_value_converts_without_float_rounding():
    assert convert_value("12.345", Numeric(12, 3)) == Decimal("12.345")


def test_boolean_text_is_parsed_as_false_not_truthy_string():
    assert convert_value("0", Boolean()) is False
    assert convert_value("true", Boolean()) is True


def test_naive_timestamps_are_normalized_to_utc():
    value = convert_value("2026-11-14T08:00:00", DateTime(timezone=True))
    assert value.tzinfo == timezone.utc
