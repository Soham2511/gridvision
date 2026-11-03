"""Customer bill prediction model package."""

from app.models.customer_bill_prediction.service import (
    CustomerBillPredictionError,
    CustomerBillPredictionService,
)

__all__ = ["CustomerBillPredictionError", "CustomerBillPredictionService"]
