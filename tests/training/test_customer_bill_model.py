from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from training.customer_bill.model import NaiveProjectionRegressor


def test_naive_projection_predicts_non_negative_month_projection():
    model = NaiveProjectionRegressor().fit(
        pd.DataFrame({"naive_projected_month_kwh": [100.0, 80.0]}),
        np.array([100.0, 80.0]),
    )
    predictions = model.predict(
        pd.DataFrame({"naive_projected_month_kwh": [120.0, -5.0]})
    )
    np.testing.assert_array_equal(predictions, np.array([120.0, 0.0]))


def test_naive_projection_requires_cutoff_feature():
    with pytest.raises(ValueError, match="Required baseline feature"):
        NaiveProjectionRegressor().fit(pd.DataFrame({"other": [1]}), np.array([1]))
