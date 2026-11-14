"""Deterministic demand forecasting and reorder calculations.

These baselines intentionally avoid training-data claims. Rolling-origin
backtesting compares their historical errors; advanced trained models and
production model selection remain separate tasks.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite, sqrt
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
    alpha: float = 0.1,
    beta: float = 0.1,
) -> Forecast:
    """Forecast daily demand using moving-average, seasonal-naive or Croston-TSB."""
    if horizon_days < 1 or horizon_days > 90:
        raise ValueError("horizon_days must be between 1 and 90")
    if window < 1:
        raise ValueError("window must be at least 1")
    if not 0 < alpha <= 1 or not 0 < beta <= 1:
        raise ValueError("Croston-TSB alpha and beta must be in (0, 1]")
    if not daily_quantities:
        raise ValueError("At least one historical daily quantity is required")
    values = [float(v) for v in daily_quantities]
    if any(not isfinite(v) for v in values):
        raise ValueError("Daily quantities must be finite numbers")
    if any(v < 0 for v in values):
        raise ValueError("Daily quantities cannot be negative")
    if model == "moving_average":
        sample = values[-max(1, min(window, len(values))):]
        daily_mean = mean(sample)
        sigma = pstdev(sample) if len(sample) > 1 else 0.0
    elif model == "seasonal_naive":
        # Repeat the most recent seven daily observations across the horizon.
        sample = values[-7:] if len(values) >= 7 else values
        daily_mean = mean(sample)
        sigma = pstdev(sample) if len(sample) > 1 else 0.0
    elif model == "croston_tsb":
        sigma = pstdev(values) if len(values) > 1 else 0.0
        first_demand_index = next(
            (index for index, value in enumerate(values) if value > 0),
            None,
        )
        if first_demand_index is None:
            daily_mean = 0.0
        else:
            # Initialise occurrence probability from the first inter-demand
            # interval and demand size from the first non-zero observation.
            demand_size = values[first_demand_index]
            occurrence_probability = 1.0 / (first_demand_index + 1)
            for value in values[first_demand_index + 1:]:
                occurrence = 1.0 if value > 0 else 0.0
                occurrence_probability += beta * (occurrence - occurrence_probability)
                if value > 0:
                    demand_size += alpha * (value - demand_size)
            daily_mean = occurrence_probability * demand_size
    else:
        raise ValueError("model must be moving_average, seasonal_naive or croston_tsb")
    predicted = (
        sum(sample[i % len(sample)] for i in range(horizon_days))
        if model == "seasonal_naive"
        else daily_mean * horizon_days
    )
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



def rolling_origin_backtest(
    daily_quantities: Sequence[float],
    horizon_days: int = 7,
    min_train_days: int = 28,
    step_days: int = 7,
) -> dict:
    """Compare the supported baselines using expanding-window backtests.

    Each origin predicts the next horizon as a total quantity. MAE is measured
    in units per horizon; WAPE and bias are percentages. These metrics evaluate
    the supplied history only and are not a guarantee of future accuracy.
    """
    if horizon_days < 1 or horizon_days > 90:
        raise ValueError("horizon_days must be between 1 and 90")
    if min_train_days < 7:
        raise ValueError("min_train_days must be at least 7")
    if step_days < 1 or step_days > 90:
        raise ValueError("step_days must be between 1 and 90")
    values = [float(value) for value in daily_quantities]
    if any(not isfinite(value) or value < 0 for value in values):
        raise ValueError("Daily quantities must be finite and non-negative")

    required_days = min_train_days + horizon_days
    if len(values) < required_days:
        return {
            "status": "insufficient_history",
            "horizon_days": horizon_days,
            "min_train_days": min_train_days,
            "step_days": step_days,
            "required_history_days": required_days,
            "available_history_days": len(values),
            "origin_count": 0,
            "models": {},
            "best_baseline_by_wape": None,
        }

    origins = range(min_train_days, len(values) - horizon_days + 1, step_days)
    results: dict[str, dict] = {}
    for model in ("moving_average", "seasonal_naive", "croston_tsb"):
        errors: list[float] = []
        signed_errors: list[float] = []
        actual_total = 0.0
        for origin in origins:
            actual = sum(values[origin:origin + horizon_days])
            predicted = forecast_demand(
                values[:origin],
                horizon_days=horizon_days,
                model=model,
            ).predicted_qty
            errors.append(abs(predicted - actual))
            signed_errors.append(predicted - actual)
            actual_total += actual

        total_absolute_error = sum(errors)
        results[model] = {
            "origin_count": len(errors),
            "ranking_eligible": len(errors) >= 3,
            "mae_horizon_units": round(mean(errors), 4) if errors else None,
            "wape_pct": (
                round(total_absolute_error / actual_total * 100, 4)
                if actual_total > 0 else None
            ),
            "bias_pct": (
                round(sum(signed_errors) / actual_total * 100, 4)
                if actual_total > 0 else None
            ),
            "actual_units_evaluated": round(actual_total, 3),
        }

    eligible = [
        (model, metrics["wape_pct"])
        for model, metrics in results.items()
        if metrics["wape_pct"] is not None
    ]
    best = (
        min(eligible, key=lambda item: item[1])[0]
        if eligible and len(origins) >= 3 else None
    )
    return {
        "status": "evaluated",
        "evaluation_method": "expanding_window_rolling_origin",
        "horizon_days": horizon_days,
        "min_train_days": min_train_days,
        "step_days": step_days,
        "required_history_days": required_days,
        "available_history_days": len(values),
        "origin_count": len(origins),
        "minimum_origins_for_ranking": 3,
        "models": results,
        "best_baseline_by_wape": best,
        "metric_notes": {
            "mae_horizon_units": "Mean absolute error in total units per forecast horizon",
            "wape_pct": "Weighted absolute percentage error over evaluated horizons",
            "bias_pct": "Positive means over-forecast; negative means under-forecast",
        },
    }

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
