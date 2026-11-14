from fastapi import APIRouter

router = APIRouter(prefix="/forecasting", tags=["forecasting"])


@router.get("/status")
def forecasting_module_status() -> dict:
    return {
        "module": "forecasting",
        "stage": "Stage 1 Foundation (forecasting pipelines scheduled for Stage 4)",
        "supported_models": ["seasonal_naive", "moving_average", "croston_tsb", "lightgbm"],
    }
