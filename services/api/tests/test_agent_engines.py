import pytest

from app.modules.forecasting.engine import calculate_reorder, forecast_demand, rolling_origin_backtest
from app.modules.pricing.engine import PricingInputs, minimum_selling_price_paise, recommend_price


def test_moving_average_forecast_is_non_negative():
    result = forecast_demand([1, 2, 3, 4, 5], horizon_days=7)
    assert result.predicted_qty == 21
    assert result.lower_bound_qty >= 0
    assert result.upper_bound_qty >= result.predicted_qty


def test_forecast_rejects_invalid_history():
    with pytest.raises(ValueError):
        forecast_demand([-1, 2])
    with pytest.raises(ValueError):
        forecast_demand([])


def test_reorder_rounds_to_supplier_pack():
    result = calculate_reorder(5, 1, 4, 6, 2, 10)
    assert result["rounded_suggested_qty"] % 10 == 0
    assert result["rounded_suggested_qty"] >= result["raw_suggested_qty"]


def test_reorder_does_not_suggest_negative_quantity():
    result = calculate_reorder(1, 0, 2, 100, 0, 5)
    assert result["rounded_suggested_qty"] == 0


def test_price_never_exceeds_mrp_or_violates_margin():
    result = recommend_price(PricingInputs(
        current_price_paise=10000, mrp_paise=12000, cost_price_paise=7000,
        min_margin_bps=1000, nearby_median_price_paise=9000,
    ))
    assert result["recommended_price_paise"] <= 12000
    assert result["recommended_price_paise"] >= 7700
    assert result["recommended_price_paise"] % 100 == 0
    assert result["constraints_passed"]


def test_expiry_discount_is_applied():
    result = recommend_price(PricingInputs(
        current_price_paise=10000, mrp_paise=12000, cost_price_paise=5000,
        days_to_expiry=2,
    ))
    assert result["expiry_discount_pct"] == 15
    assert result["recommended_price_paise"] < 10000


def test_expired_product_is_not_priced():
    with pytest.raises(ValueError):
        recommend_price(PricingInputs(
            current_price_paise=10000, mrp_paise=12000, cost_price_paise=5000,
            days_to_expiry=0,
        ))


def test_infeasible_margin_and_daily_limit_is_rejected():
    with pytest.raises(ValueError):
        recommend_price(PricingInputs(
            current_price_paise=10000, mrp_paise=12000, cost_price_paise=10100,
            min_margin_bps=1000,
        ))



def test_rolling_origin_backtest_compares_both_baselines():
    result = rolling_origin_backtest(
        [5.0] * 70,
        horizon_days=7,
        min_train_days=28,
        step_days=7,
    )
    assert result["status"] == "evaluated"
    assert result["origin_count"] == 6
    assert set(result["models"]) == {"moving_average", "seasonal_naive", "croston_tsb"}
    for metrics in result["models"].values():
        assert metrics["origin_count"] == 6
        assert metrics["mae_horizon_units"] == 0
        assert metrics["wape_pct"] == 0
        assert metrics["bias_pct"] == 0


def test_rolling_origin_backtest_reports_insufficient_history():
    result = rolling_origin_backtest(
        [2.0] * 34,
        horizon_days=7,
        min_train_days=28,
    )
    assert result["status"] == "insufficient_history"
    assert result["origin_count"] == 0
    assert result["required_history_days"] == 35


def test_rolling_origin_backtest_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        rolling_origin_backtest([1.0] * 40, min_train_days=6)
    with pytest.raises(ValueError):
        rolling_origin_backtest([1.0, float("nan")] + [1.0] * 38)



def test_rolling_origin_does_not_rank_a_baseline_from_one_window():
    result = rolling_origin_backtest(
        [4.0] * 35,
        horizon_days=7,
        min_train_days=28,
        step_days=7,
    )
    assert result["origin_count"] == 1
    assert result["minimum_origins_for_ranking"] == 3
    assert result["best_baseline_by_wape"] is None
    assert all(not metrics["ranking_eligible"] for metrics in result["models"].values())



def test_croston_tsb_handles_intermittent_demand_and_zero_demand():
    intermittent = forecast_demand(
        [0, 0, 10, 0, 0, 0, 0, 0],
        horizon_days=7,
        model="croston_tsb",
    )
    assert intermittent.predicted_qty >= 0
    assert intermittent.predicted_qty < 10

    no_demand = forecast_demand(
        [0] * 40,
        horizon_days=7,
        model="croston_tsb",
    )
    assert no_demand.predicted_qty == 0


def test_croston_tsb_rejects_invalid_smoothing_parameters():
    with pytest.raises(ValueError):
        forecast_demand([0, 1, 0, 2], model="croston_tsb", alpha=0)
    with pytest.raises(ValueError):
        forecast_demand([0, 1, 0, 2], model="croston_tsb", beta=1.1)



@pytest.mark.parametrize(
    ("days_to_expiry", "expected_discount"),
    [(3, 15.0), (4, 8.0), (8, 3.0), (15, 0.0)],
)
def test_expiry_markdown_tiers(days_to_expiry, expected_discount):
    result = recommend_price(PricingInputs(
        current_price_paise=10000,
        mrp_paise=12000,
        cost_price_paise=5000,
        days_to_expiry=days_to_expiry,
    ))
    assert result["expiry_discount_pct"] == expected_discount
    assert result["recommended_price_paise"] <= 10000


def test_competitor_price_signal_respects_margin_and_daily_movement_limits():
    result = recommend_price(PricingInputs(
        current_price_paise=10000,
        mrp_paise=15000,
        cost_price_paise=8500,
        min_margin_bps=1000,
        nearby_median_price_paise=20000,
    ))
    assert 9500 <= result["recommended_price_paise"] <= 11000
    assert result["recommended_price_paise"] % 100 == 0


def test_competitor_discount_cannot_break_minimum_margin_floor():
    result = recommend_price(PricingInputs(
        current_price_paise=10000,
        mrp_paise=12000,
        cost_price_paise=9500,
        min_margin_bps=1000,
        nearby_median_price_paise=5000,
    ))
    assert result["recommended_price_paise"] == 10600
    assert result["expected_margin_bps"] >= 1000


def test_excess_stock_pressure_only_applies_bounded_markdown():
    neutral = recommend_price(PricingInputs(
        current_price_paise=10000, mrp_paise=12000, cost_price_paise=5000,
    ))
    pressured = recommend_price(PricingInputs(
        current_price_paise=10000, mrp_paise=12000, cost_price_paise=5000,
        stock_pressure_factor=3.0,
    ))
    assert neutral["recommended_price_paise"] == 10000
    assert pressured["recommended_price_paise"] == 9000
    assert pressured["recommended_price_paise"] < neutral["recommended_price_paise"]


def test_demand_signal_is_considered_without_bypassing_price_guardrails():
    result = recommend_price(PricingInputs(
        current_price_paise=10000,
        mrp_paise=15000,
        cost_price_paise=5000,
        demand_signal_price_paise=14000,
    ))
    assert result["recommended_price_paise"] == 11000
    assert "Demand signal considered" in result["explanation"]


def test_pricing_rejects_non_positive_stock_pressure():
    with pytest.raises(ValueError):
        recommend_price(PricingInputs(
            current_price_paise=10000,
            mrp_paise=12000,
            cost_price_paise=5000,
            stock_pressure_factor=0,
        ))



def test_minimum_margin_floor_uses_gross_margin_on_selling_price():
    assert minimum_selling_price_paise(9500, 1000) == 10600
    assert minimum_selling_price_paise(9500, 1000, clearance_allowed=True) == 9500
    assert minimum_selling_price_paise(10000, 0) == 10000


def test_minimum_margin_floor_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        minimum_selling_price_paise(10000, 9001)
    with pytest.raises(ValueError):
        minimum_selling_price_paise(-1, 1000)
