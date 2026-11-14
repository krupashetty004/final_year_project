"""Deterministic demand forecasting and reorder calculations.

These baselines intentionally avoid training-data claims. They are suitable for
small-store histories and provide a stable fallback until model backtesting is
available.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt
from statistics import mean, pstdev
from typing import Sequence


@dataclass(frozen=True)
class Forecast:
    model_name: str
    daily_mean: float
    daily_sigma: float
    horizon_days: int
    predicted_qty: float
    lower_bound_qty: float
    upper_bound_qty: float


def forecast_demand(
    daily_quantities: Sequence[float],
    horizon_days: int = 7,
    model: str = "moving_average",
    window: int = 28,
) -> Forecast:
    """Forecast non-negative daily demand using moving-average or seasonal-naive."""
    if horizon_days < 1 or horizon_days > 90:
        raise ValueError("horizon_days must be between 1 and 90")
    if not daily_quantities:
        raise ValueError("At least one historical daily quantity is required")
    values = [float(v) for v in daily_quantities]
    if any(v < 0 for v in values):
        raise ValueError("Daily quantities cannot be negative")
    if model == "moving_average":
        sample = values[-max(1, min(window, len(values))):]
        daily_mean = mean(sample)
        sigma = pstdev(sample) if len(sample) > 1 else 0.0
    elif model == "seasonal_naive":
        # Repeat the most recently observed 7-day pattern where available.
        sample = values[-7:] if len(values) >= 7 else values
        daily_mean = mean(sample)
        sigma = pstdev(sample) if len(sample) > 1 else 0.0
    else:
        raise ValueError("model must be moving_average or seasonal_naive")
    predicted = daily_mean * horizon_days
    spread = 1.645 * sigma * sqrt(horizon_days)
    return Forecast(
        model_name=model,
        daily_mean=round(daily_mean, 3),
        daily_sigma=round(sigma, 4),
        horizon_days=horizon_days,
        predicted_qty=round(predicted, 3),
        lower_bound_qty=round(max(0.0, predicted - spread), 3),
        upper_bound_qty=round(predicted + spread, 3),
    )


def calculate_reorder(
    daily_demand: float,
    daily_sigma: float,
    lead_time_days: int,
    available_qty: float,
    incoming_qty: float = 0.0,
    supplier_pack_size: float = 1.0,
    service_z: float = 1.65,
) -> dict:
    """Calculate ROP and pack-rounded order quantity; does not place an order."""
    if min(daily_demand, daily_sigma, available_qty, incoming_qty) < 0:
        raise ValueError("Demand, uncertainty and inventory quantities cannot be negative")
    if lead_time_days < 1 or lead_time_days > 60:
        raise ValueError("lead_time_days must be between 1 and 60")
    if supplier_pack_size <= 0 or service_z < 0:
        raise ValueError("supplier_pack_size must be positive and service_z non-negative")
    lead_demand = daily_demand * lead_time_days
    safety = service_z * daily_sigma * sqrt(lead_time_days)
    rop = lead_demand + safety
    raw = max(0.0, rop - available_qty - incoming_qty)
    rounded = ceil(raw / supplier_pack_size) * supplier_pack_size if raw else 0.0
    return {
        "expected_lead_time_demand_qty": round(lead_demand, 3),
        "safety_stock_qty": round(safety, 3),
        "reorder_point_qty": round(rop, 3),
        "raw_suggested_qty": round(raw, 3),
        "rounded_suggested_qty": round(rounded, 3),
    }
