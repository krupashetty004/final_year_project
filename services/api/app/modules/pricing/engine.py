"""Rule-based, approval-gated pricing recommendation engine.

This engine uses transparent deterministic rules. It is not presented as a
trained price-elasticity model; historical elasticity estimation remains a
separately validated model task.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from typing import Optional


@dataclass(frozen=True)
class PricingInputs:
    current_price_paise: int
    mrp_paise: int
    cost_price_paise: int
    min_margin_bps: int = 1000
    nearby_median_price_paise: Optional[int] = None
    demand_signal_price_paise: Optional[int] = None
    days_to_expiry: Optional[int] = None
    stock_pressure_factor: float = 1.0
    clearance_allowed: bool = False


def minimum_selling_price_paise(
    cost_price_paise: int,
    min_margin_bps: int,
    clearance_allowed: bool = False,
) -> int:
    """Return the lowest whole-rupee price satisfying gross margin on selling price.

    Margin basis points are defined as (selling price - cost) / selling price.
    Explicit clearance can reduce the floor to cost, but never below ₹1.
    """
    if cost_price_paise < 0:
        raise ValueError("Cost price cannot be negative")
    if not 0 <= min_margin_bps <= 9000:
        raise ValueError("min_margin_bps must be between 0 and 9000")
    denominator = 10000 if clearance_allowed else 10000 - min_margin_bps
    raw_floor_paise = (
        cost_price_paise * 10000 + denominator - 1
    ) // denominator
    whole_rupee_floor = ((raw_floor_paise + 99) // 100) * 100
    return max(100, whole_rupee_floor)


def recommend_price(data: PricingInputs) -> dict:
    """Generate a whole-rupee recommendation subject to all configured limits."""
    if min(data.current_price_paise, data.mrp_paise) <= 0 or data.cost_price_paise < 0:
        raise ValueError("Prices must be positive (cost may be zero)")
    if data.current_price_paise > data.mrp_paise:
        raise ValueError("Current price cannot exceed MRP")
    if not 0 <= data.min_margin_bps <= 9000:
        raise ValueError("min_margin_bps must be between 0 and 9000")
    if data.stock_pressure_factor <= 0:
        raise ValueError("stock_pressure_factor must be positive")
    if data.days_to_expiry is not None and data.days_to_expiry <= 0:
        raise ValueError("Expired products must not receive a selling-price recommendation")

    candidates = [float(data.current_price_paise)]
    reasons = ["Current price used as baseline"]
    if data.nearby_median_price_paise and data.nearby_median_price_paise > 0:
        candidates.append(float(data.nearby_median_price_paise))
        reasons.append("Nearby verified-store median considered")
    if data.demand_signal_price_paise and data.demand_signal_price_paise > 0:
        candidates.append(float(data.demand_signal_price_paise))
        reasons.append("Demand signal considered")
    target = sum(candidates) / len(candidates)

    # Stock pressure is treated as excess-stock pressure only. Scarcity never
    # causes an automatic price increase.
    if data.stock_pressure_factor > 1:
        discount = min(0.10, (data.stock_pressure_factor - 1) * 0.05)
        target *= 1.0 - discount
        reasons.append("Excess-stock pressure considered")

    expiry_discount = 0.0
    if data.days_to_expiry is not None:
        if data.days_to_expiry <= 3:
            expiry_discount = 0.15
        elif data.days_to_expiry <= 7:
            expiry_discount = 0.08
        elif data.days_to_expiry <= 14:
            expiry_discount = 0.03
        if expiry_discount:
            target *= 1.0 - expiry_discount
            reasons.append(f"Expiry markdown of {expiry_discount:.0%} considered")

    # Storage is integer paise; recommendation is rounded down to whole rupees.
    target = floor(target / 100) * 100
    margin_floor = minimum_selling_price_paise(
        data.cost_price_paise,
        data.min_margin_bps,
        data.clearance_allowed,
    )
    lower_daily = ceil(data.current_price_paise * 0.90 / 100) * 100
    upper_daily = floor(data.current_price_paise * 1.10 / 100) * 100
    feasible_floor = max(margin_floor, lower_daily)
    feasible_ceiling = min(data.mrp_paise, upper_daily)
    if feasible_floor > feasible_ceiling:
        raise ValueError(
            "No price satisfies MRP, minimum-margin and 10% daily-movement constraints"
        )
    target = max(feasible_floor, min(target, feasible_ceiling))
    margin_bps = int(round((target - data.cost_price_paise) / target * 10000))
    return {
        "recommended_price_paise": int(target),
        "expiry_discount_pct": round(expiry_discount * 100, 2),
        "expected_margin_bps": margin_bps,
        "constraints_passed": True,
        "explanation": "; ".join(reasons) + "; owner approval required before any price change.",
    }
