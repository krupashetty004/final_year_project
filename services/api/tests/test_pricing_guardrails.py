from datetime import datetime, timezone

import pytest

from app.core.pricing_guardrails import validate_daily_price_change


def test_price_change_within_ten_percent_is_allowed():
    validate_daily_price_change(10000, 9000, None)
    validate_daily_price_change(10000, 11000, None)


@pytest.mark.parametrize("proposed", [8999, 11001])
def test_price_change_outside_ten_percent_is_rejected(proposed):
    with pytest.raises(ValueError, match="10%"):
        validate_daily_price_change(10000, proposed, None)


def test_no_op_price_approval_does_not_use_daily_change_allowance():
    now = datetime(2026, 11, 14, 1, 0, tzinfo=timezone.utc)
    changed_today_ist = datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)
    validate_daily_price_change(10000, 10000, changed_today_ist, now)


def test_india_local_midnight_is_used_not_utc_midnight():
    # Both instants are on 14 Nov in India, but on different UTC dates.
    now = datetime(2026, 11, 14, 1, 0, tzinfo=timezone.utc)
    previous = datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="already been recorded"):
        validate_daily_price_change(10000, 10500, previous, now)


def test_price_change_is_allowed_after_india_local_midnight():
    now = datetime(2026, 11, 14, 1, 0, tzinfo=timezone.utc)
    previous = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
    validate_daily_price_change(10000, 10500, previous, now)


def test_naive_legacy_timestamp_is_treated_as_utc():
    now = datetime(2026, 11, 14, 1, 0, tzinfo=timezone.utc)
    previous = datetime(2026, 11, 13, 20, 0)
    with pytest.raises(ValueError, match="already been recorded"):
        validate_daily_price_change(10000, 10500, previous, now)
