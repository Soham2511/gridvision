# `hybrid_grid_2018.joblib` model reference

## Purpose

`hybrid_grid_2018.joblib`, stored alongside this model card, is a grid-level
energy forecasting package created from the supplied 2018 workflow. It
predicts `target_energy` for coarse grid IDs using features available at a
forecast origin and calendar features for the target time. The trained models
support horizons from 1 to 24 hours.

The target is the total normalized building energy in a grid at the future
timestamp, in the source dataset's energy units (kWh). The model is specific
to the 2018 dataset, its grid IDs, feature definitions, and preprocessing. It
should not be assumed to generalize to other years, grids, or feature-generation
logic without evaluation.

## Why it is a hybrid model

The package contains two LightGBM regressors:

1. **Original-target model** predicts `target_energy` directly.
2. **Log-target model** is trained on `log1p(target_energy)`. Its predictions
   are converted back with `expm1(max(prediction, 0))`, guaranteeing
   non-negative predictions.

The log-target version performed better on some grids, particularly at low
energy scales, while the original-target model performed better on others.
Rather than use one model for all grids, the notebook compared both models'
MAE separately for every grid on the validation period. It selected the
log-target model where its validation MAE was lower, and the original-target
model otherwise. This chose the log-target model for 39 grids and the
original-target model for 14 grids, out of 53.

The routing decision is fixed from validation results; December test
observations are not used to choose a route.

## Training details recorded for the supplied artifact

- **Training period:** target timestamps from January through September 2018.
- **Validation period:** target timestamps from October through November 2018.
- **Test period:** target timestamps in December 2018.
- **Training sample used for the notebook's two model fits:** 1,500,000 rows,
  sampled reproducibly with random seed 42 from the training split.
- **Validation rows:** 1,710,257.
- **December test rows:** 869,147 across 53 grids and 24 forecast horizons.
- **Model family:** LightGBM regressor, squared-error regression objective.
- **Configured maximum estimators:** 1,200, with early stopping after 60 rounds
  without validation improvement.
- **Recorded best iterations:** 133 for the original-target model and 96 for
  the log-target model.
- **Shared parameters:** learning rate 0.05, 31 leaves, unlimited tree depth,
  minimum child samples 100, row subsampling 0.8, column subsampling 0.8,
  L2 regularization 1.0, maximum bin count 127, random seed 42, and 4 jobs.

The supplied workflow checks that the model, saved feature list, and
prediction matrix have the same feature order.

## Feature inputs

The saved artifact expects these 36 features in this exact order:

1. `forecast_horizon_hours`
2. `total_building_area_m2`
3. `total_footprint_area_m2`
4. `centroid_latitude`
5. `centroid_longitude`
6. `building_count`
7. `Commercial_count`
8. `Industrial_count`
9. `Institutional_count`
10. `Recreational_count`
11. `Residential_count`
12. `energy_at_origin`
13. `energy_lag_1h`
14. `energy_lag_24h`
15. `energy_lag_168h`
16. `energy_lag_336h`
17. `energy_lag_720h`
18. `energy_mean_24h`
19. `energy_std_24h`
20. `energy_count_24h`
21. `energy_mean_7d`
22. `energy_std_7d`
23. `energy_count_7d`
24. `energy_mean_30d`
25. `energy_std_30d`
26. `energy_count_30d`
27. `target_month`
28. `target_day_of_month`
29. `target_day_of_week`
30. `target_hour`
31. `target_day_of_year`
32. `target_is_weekend`
33. `target_hour_sin`
34. `target_hour_cos`
35. `target_day_of_year_sin`
36. `target_day_of_year_cos`

The target year is intentionally not in this feature list. Use the saved
`feature_columns_2018.joblib` in this directory rather than building a
differently ordered list by hand.

## Notebook evaluation results

The figures below are the recorded results supplied for this artifact.
MAE and RMSE are in the target's energy units; lower is better. Higher R² is
better. Persistence means predicting that future energy equals
`energy_at_origin`.

### Validation results

| Model | Rows | MAE | RMSE | R² | Negative predictions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Persistence baseline | 1,710,257 | 1,521.9812 | 4,135.2313 | 0.4508 | 0.0000% |
| Original-target LightGBM | 1,710,257 | 397.2202 | 951.2364 | 0.9709 | 9.5689% |
| Log-target LightGBM | 1,710,257 | 463.8931 | 1,285.5355 | 0.9469 | 0.0000% |

The direct-target model had the best overall validation scores, but it could
produce negative forecasts. The per-grid comparison showed the log-target
model had lower validation MAE for 39 grids, motivating per-grid routing
rather than choosing one model globally.

### December test results

| Model | Rows | MAE | RMSE | R² | Negative predictions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Persistence baseline | 869,147 | 1,301.1374 | 3,719.2812 | 0.5068 | 0.0000% |
| Original-target LightGBM | 869,147 | 528.2979 | 1,086.5981 | 0.9579 | 7.7034% |
| Log-target LightGBM | 869,147 | 615.5913 | 1,472.5160 | 0.9227 | 0.0000% |
| Validation-selected hybrid | 869,147 | 524.0478 | 1,095.8606 | 0.9572 | 0.0000% |

On this test set the hybrid's MAE was slightly lower than the original model's
(524.0478 versus 528.2979), and the hybrid beat persistence on MAE for 44 of
53 grids. The hybrid did **not** improve every metric: its RMSE was higher and
its R² slightly lower than the original-target model. By forecast horizon,
the notebook reports the hybrid beat the original model and persistence on
MAE for 23 of 24 horizons. These are historical notebook results, not a
guarantee for new data.

## Artifact contents

The joblib file is a dictionary containing:

- `original_model`: fitted `LGBMRegressor`.
- `log_model`: fitted `LGBMRegressor` for the log-transformed target.
- `features`: the ordered list of 36 feature names.
- `routing`: a DataFrame with `grid_id` and `selected_model` (`original` or
  `log`) for each of the 53 grids.
- `config`: model description, training year, target, transforms, and routing
  metadata.

The bundle and its ordered feature list are both stored in this directory.
Keep them together when moving or versioning the model.

**Security:** joblib files are pickle-based. Load this artifact only if it came
from a trusted source.

## Using the saved model

From the repository root, set the package path and create a prediction parquet
from a prepared dataset:

```powershell
$env:PYTHONPATH = "airflow\2_government_load_prediction"
.\.venv\Scripts\python.exe -m grid_forecasting_pipeline predict `
  --input data\airflow\government\training_ready_2018.parquet `
  --model mlflow\government\hybrid_grid_2018.joblib `
  --output data\airflow\government\predictions_2018.parquet
```

The input must contain `id.grid.coarse` and all 36 features. The prediction
file includes the selected model and `prediction`; if `target_energy` exists
in the input, the output includes it for downstream evaluation. The `predict`
command generates predictions but does not calculate MAE, RMSE, or R².

The pipeline's separate `train` command trains new model objects using the
current configured training procedure. Its output is not guaranteed to be
bit-for-bit identical to this notebook-trained artifact, and the notebook
metrics above do not automatically apply to a newly trained model.

## Source and reproducibility

The source notebook is not included in this repository. Training details,
routing rationale, and evaluation figures in this card are the historical
values supplied with the artifact; they have not been recalculated from the
shared GridVision sample. For a new model version, rerun evaluation on a
held-out dataset and record the model artifact version, data version,
feature-list version, split boundaries, and metrics together.
