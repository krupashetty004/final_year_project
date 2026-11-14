from fastapi import APIRouter

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.get("/status")
def pricing_module_status() -> dict:
    return {
        "module": "smart_pricing",
        "stage": "Stage 1 Foundation (pricing engine scheduled for Stage 5)",
        "enforced_constraints": [
            "selling_price <= mrp",
            "selling_price >= cost * (1 + min_margin) unless batch clearance enabled",
            "max_daily_change_pct <= 10",
            "max_one_approved_change_per_day",
            "whole_rupee_rounding",
            "no_personalized_pricing",
        ],
    }
