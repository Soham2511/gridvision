# Model Card: customer-bill-prediction v1

## Summary

- **Task:** Estimate a residential customer's target-month energy consumption (kWh) from cutoff-time observations.
- **Registered alias:** `champion`
- **Selected estimator:** `naive_month_projection`
- **MLflow run:** `d976cacc47074ddf88d76535c22d63db`
- **Training dataset version:** `20261021T220657-5b464697`
- **Dataset quality passed:** `True`

## Intended use

This model is an experimental, decision-support estimate for customer bill prediction. It is not a meter reading, a guaranteed invoice, or a substitute for a utility's billing system. The configured tariff is illustrative and must be replaced with the customer's applicable tariff before interpreting bill estimates.

## Data and evaluation

- **Dataset path:** `D:\Projects\gridvision-app\data\gold\customer_gold.parquet`
- **Versioned dataset snapshot:** `D:\Projects\gridvision-app\data\metadata\dataset_versions\customer_gold\20261021T220657-5b464697.parquet`
- **Dataset rows recorded in manifest:** `36000`
- **Target:** `target_month_kwh` (full target-month kWh)
- **Split:** Chronological by month into train, validation, and held-out test sets; rows from a month are kept together.
- **Partition month ranges:** `{"test": "2018-11-01 to 2018-12-01", "train": "2018-01-01 to 2018-08-01", "validation": "2018-09-01 to 2018-10-01"}`
- **Validation metrics:** `{"baseline_validation_mae_kwh": 29.684995746341613, "selected_validation_mae_kwh": 29.684995746341613, "tuned_cv_mae_kwh": 126.53652227577602, "tuned_validation_mae_kwh": 70.05106298352254}`
- **Held-out test metrics:** `{"mae_kwh": 20.020716925374305, "r2": 0.9982470190706677, "rmse_kwh": 51.19122349225592}`
- **Best tuned candidate parameters:** `{"l2_regularization": 1.0, "learning_rate": 0.05, "max_iter": 120, "max_leaf_nodes": 15}`
- **Input features:** building_area_m2, footprint_area_m2, effective_year_built, id_grid_finer, latitude, longitude, cutoff_day, days_in_month, month_of_year, month_sin, month_cos, prior_month_kwh, prior_month_kwh_per_m2, observed_hours_to_cutoff, cumulative_energy_kwh, recent_7d_energy_kwh, recent_7d_mean_hourly_kwh, mean_hourly_energy_to_cutoff, cumulative_energy_per_m2, naive_projected_month_kwh, idf_kw, specific_use_type, building_type, vintage, usetype

## Limitations and risks

- Evaluation is based on the supplied sampled dataset and may not represent other buildings, regions, seasons, or meter behavior.
- The source dataset does not provide customer-specific billing tariffs; any currency estimate uses an illustrative configured tariff.
- Performance can degrade under missing, delayed, shifted, or out-of-distribution meter readings or building attributes.
- The prediction is for monthly energy consumption; the model does not verify a final utility invoice.
- Validate data quality, local tariff rules, and performance on representative recent data before operational use.

## Reproducibility

- **Features and target:** recorded above and in the MLflow model signature.
- **Selected model parameters:** recorded above and as MLflow run parameters.
- **Dataset lineage:** `{"customer_silver": "20261021T220654-6725749e"}`
- **Model artifact:** logged with the MLflow run; a local pickle is also exported alongside its metadata.
