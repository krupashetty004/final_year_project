"""Shared price-movement and daily-change guardrails."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")


def validate_daily_price_change(
    current_price_paise: int,
    proposed_price_paise: int,
    last_price_changed_at_utc: datetime | None,
    now_utc: datetime | None = None,
) -> None:
    """Raise ValueError when a real price change violates the shared policy.

    Price movement is limited to +/-10% from the current price, rounded to
    whole rupees. At most one actual price change is permitted per India-local
    calendar day. No-op approvals do not consume the daily change allowance.
    """
    current = int(current_price_paise)
    proposed = int(proposed_price_paise)
    if current <= 0 or proposed <= 0:
        raise ValueError("Prices must be positive")
    if proposed == current:
        return

    # Integer arithmetic avoids floating-point boundary drift in paise.
    lower = ((current * 9 + 999) // 1000) * 100
    upper = (current * 11 // 1000) * 100
    if not lower <= proposed <= upper:
        raise ValueError("Price change exceeds the +/-10% movement guardrail")

    if last_price_changed_at_utc is None:
        return

    changed_at = last_price_changed_at_utc
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if changed_at.astimezone(INDIA_TIMEZONE).date() == now.astimezone(INDIA_TIMEZONE).date():
        raise ValueError("A price change has already been recorded for this SKU today")
