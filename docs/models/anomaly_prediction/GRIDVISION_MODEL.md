# GridVision Model: Anomaly Detection and Spatial Localization

## What this implementation does

This project follows the multi-stage approach in
[`GridVision_Electricity_Anomaly_Detection_and_Spatial_Localization.docx`](./GridVision_Electricity_Anomaly_Detection_and_Spatial_Localization.docx):

1. Audit and validate the hourly parquet data.
2. Build customer-specific, causal load baselines and point features.
3. Detect point/sequence anomalies with a binary Random Forest using causal time-domain, FFT, and multi-scale Haar-wavelet features.
4. Extract a ±12-hour anomalous window and characterize it with time-domain, FFT, and wavelet features.
5. Apply deterministic signal rules to label `spike`, `drop`, `zero_block`, or `flatline`; no multiclass type model is used.
6. Convert the existing per-customer anomaly windows to H3 cells and form spatial-temporal events.
7. Classify event scope as `SINGLE_CUSTOMER`, `LOCAL_AREA`, or `MULTI_AREA`.
8. Evaluate reconstructed events after grouping and save summaries and validation plots.

The implementation is a sampled, reproducible baseline, not a production grid-protection system.

The parent GridVision Flask API and React route documented in [`GRIDVISION_APPLICATION.md`](./GRIDVISION_APPLICATION.md) run this saved bundle against the configured parquet source and display inference/localization results. The application does not retrain the bundle and does not change the detector, feature engineering, or anomaly-type rules.

The streaming source-to-model-input conversion, Airflow training DAG, MLflow
metrics/artifacts, project logging, and pytest instructions are documented in
[`GRIDVISION_TRAINING_PIPELINE.md`](./GRIDVISION_TRAINING_PIPELINE.md).

## Source data and important limitation

The input is `data/anomaly_prediction/synthetic_2019_normal.parquet`. Its metadata reports 87,600,000 rows, 365 daily row groups, and 10,000 customers. The inspected first day has 240,000 rows and no missing energy readings. Parquet statistics across all 365 row groups report `is_anomaly` minimum and maximum as false, with no null labels. It is therefore a normal-only dataset and cannot provide real anomaly ground truth.

To make evaluation possible without pretending otherwise, the notebook injects controlled spike, drop, sustained-zero, and flatline events into separate copies of the train, validation, and test customer data. Injection targets are held separately from model features. Reported detection and classification metrics measure performance on these synthetic patterns only; they do not establish expected performance on real faults.

The available energy input is `normalized_building_energy_kwh`, not a guaranteed raw-kWh measurement. Recalibrate before applying the model to different units or customer populations.

## Leakage controls and split design

- The source-provided `is_anomaly`, `anomaly_type`, `anomaly_event_id`, `event_scope`, `area_id`, `start_time`, `end_time`, `severity`, and `original_energy_kwh` fields are excluded from model inputs. In particular, `original_energy_kwh` is never supplied to a model.
- All 10,000 customer IDs are partitioned first (80% train, 10% validation, 10% test). The default bounded sample then selects 200 train, 100 validation, and 100 test customers from those disjoint sets. No sampled customer occurs in more than one partition.
- Each customer partition uses a chronological window: the first 70% for training, the next 15% for validation, and the final 15% for test. For this file, the boundaries are 2019-09-13 12:00 and 2019-11-07 06:00.
- The load baseline and trailing features shift measurements by one hour before computing rolling statistics. All per-point FFT and wavelet calculations use trailing 25-hour residual windows, so no future load contributes to a point's feature vector.
- The binary detector is trained only from normal training rows and synthetic positive events injected into training customers/time. Its validation threshold is selected on independent validation-customer synthetic events, then evaluated once on test.
- Spike/drop rule cutoffs are quantiles learned from training-normal residuals. Zero-block and flatline labels use explicit run-length/context rules. The four type labels are not learned by a multiclass classifier.
- Test customers and the final chronological time window are not used in detector fitting, rule-threshold learning, or alert-threshold selection.
- The sampled records are checked for missing required values, duplicate customer-hours, and non-hourly gaps. The pipeline raises a descriptive error rather than silently dropping or interpolating irregular readings.

The default customer sampling bounds memory and runtime while preserving complete customer groups. It does **not** train or score all 10,000 customers. Increase the sample counts in the configuration only after measuring available memory and runtime.

## Feature and model design

### Point detection

The trailing robust baseline uses the prior 24-hour median, falling back to the prior 168-hour median where available. The point detector uses 30 features: log residual, relative deviation, one- and 24-hour changes, baseline-normalized rolling variability, zero/flatline run lengths, cyclic calendar encodings, seven FFT features, and eight multi-scale Haar features.

The FFT is calculated from each trailing window of log residuals and contributes dominant frequency, total spectral energy, normalized spectral entropy, spectral centroid, peak magnitude, and low/high-band energy. Haar detail coefficients at 1-, 2-, 4-, and 8-hour scales contribute trailing coefficient energies, cross-scale variance/magnitude, scale entropy, and dominant scale. These signal-characterization features are detector inputs, not merely post-detection classifier features.

The binary Random Forest is trained on all injected positive training points plus up to 200,000 sampled normal training points (with class balancing). The starting alert score quantile is recorded; the final threshold is selected by validation F1 on held-out synthetic events. This allows FFT/wavelet patterns to directly influence anomaly detection.

### Post-detection characterization and rule labels

After detection, the pipeline extracts a 25-hour window (±12 hours) and computes time-domain statistics (mean, median, extrema, standard deviation, variance, range, RMS, skew, kurtosis, slope/rate, deviation, and pre/post-event statistics), temporal duration/recovery, FFT peak/frequency/band-energy/entropy features, and Haar-wavelet coefficient energy/variance/maximum/entropy/scale-ratio features.

The final type is determined without a multiclass model:

1. Three or more consecutive near-zero values while load is expected → `zero_block`.
2. Six or more repeated readings, with prior variability and a sustained level shift from the expected baseline → `flatline`.
3. Positive deviation above the 99.9th percentile of training-normal residual behavior → `spike`.
4. Negative deviation below the 0.1th percentile → `drop`.
5. If a detected point does not meet a specialized sequence or learned-tail rule, its residual sign supplies the fallback label.

These are operational starting rules, not universal physical definitions; tune run lengths and contextual cutoffs on independently labeled validation events.

### Spatial-temporal localization and event scope

The localization stage is separate from the detector and anomaly-type rules. It consumes the existing per-customer anomaly-window output (`OBJECTID`, `start_time`, `end_time`, `anomaly_type`, `latitude`, `longitude`, and `max_anomaly_score`), normalizes those fields to a customer-level event record, and preserves the anomaly type independently from the event scope.

Each coordinate is assigned a deterministic H3 cell. H3 resolution and haversine DBSCAN radius are configurable in `PipelineConfig`; defaults are resolution 8, 5 km radius, and two unique customers per DBSCAN cluster. DBSCAN is fit on one representative location per customer, so a customer's repeated detected windows cannot artificially satisfy the density minimum. DBSCAN noise points are kept distinct and are not combined into multi-customer events just because they occurred at similar times. The output describes **geographic clusters only**; without feeder, transformer, or substation identifiers it does not identify electrical network assets.

Temporal correlation requires at least one configured condition: start times within 30 minutes, interval overlap of at least 25% of the shorter interval, or an interval gap no greater than 60 minutes. These configurable defaults are not learned from ground truth. Event components are transitive: A can be connected to C through B even if A and C do not directly meet the temporal rule. Customers in a common dense spatial cluster may form a local event when temporally related; two or more distinct dense clusters can form a `MULTI_AREA` event only when temporally related as well. A lone affected customer is `SINGLE_CUSTOMER`; multiple affected customers in one cluster are `LOCAL_AREA`. Scope never overwrites `anomaly_type`.

The modular API is in `backend/app/models/anomaly_prediction/runtime/gridvision_event_localization.py`: `prepare_anomaly_records`, `assign_spatial_cells`, `spatial_clustering`, `temporal_correlation`, `form_events`, `classify_event_scope`, `generate_event_summary`, `evaluate_events`, and `visualize_events`.

Ground-truth injected-event IDs and labels are not passed into H3 assignment, clustering, temporal correlation, event formation, or scope classification. They are passed only to the post-localization event evaluator. The current synthetic generator creates independent per-customer events rather than labeled common outages or multi-area events; therefore event metrics can check reconstruction against individual synthetic intervals but cannot validate whether `LOCAL_AREA` or `MULTI_AREA` matches real incident scope.

## Setup and execution

From the parent GridVision project root:

```bash
python automation.py --anomaly-only
```

Or open and run [`notebooks/gridvision_anomaly_detection.ipynb`](../notebooks/gridvision_anomaly_detection.ipynb) from top to bottom. The notebook has a markdown heading and a corresponding code cell for each stage. The first run reads the parquet file once to inspect its schema and again in bounded batches to select the sampled customers; it may take several minutes and requires memory for roughly 3.5 million sampled rows and engineered features.

Important settings are defined in `PipelineConfig` in `backend/app/models/anomaly_prediction/runtime/gridvision_pipeline.py`: customer sample sizes, normal-to-positive training ratio, number of synthetic events per class, starting score quantile, run-length rules, random seed, and artifact paths.

Spatial-temporal settings are also configurable there: `h3_resolution`, `spatial_radius_km`, `spatial_dbscan_min_customers`, `maximum_start_time_difference_minutes`, `minimum_temporal_overlap`, and `maximum_interval_gap_minutes`.

Run the focused leakage and event-generation checks with:

```bash
python -m unittest discover -s tests -v
```

## Outputs

- `models/anomaly_prediction/gridvision_anomaly_model.joblib` — fitted binary Random Forest detector, thresholds, type-rule cutoffs, feature contract, evaluation metrics, and localization note.
- `reports/anomaly_prediction/evaluation_metrics.json` — source profile, split integrity, temporal boundaries, validation/test metrics, and limitations.
- `reports/anomaly_prediction/` — retained event/window CSVs, event localization metrics, and event visualizations.

To score new, chronologically ordered customer-hour readings, use the same five input fields (`OBJECTID`, `timestamp`, `normalized_building_energy_kwh`, `latitude`, `longitude`) and pass sufficient prior history for the rolling baseline:

```python
import sys
sys.path.insert(0, "backend/app/models/anomaly_prediction/runtime")
from gridvision_pipeline import predict_point_anomalies

predictions = predict_point_anomalies(
    incoming_customer_history,
    "models/anomaly_prediction/gridvision_anomaly_model.joblib",
)
```

The prediction helper returns input identifiers, timestamp, coordinates, observed energy, anomaly score, thresholded `is_anomaly` flag, and a deterministic `anomaly_type` for detected readings. Keep history grouped by customer and preserve timestamp order. Since this point API is causal, its FFT/wavelet windows use only present and earlier observations. Do not send source labels or post-event/original values as predictors.

### Exact prediction input columns

The raw inference dataframe must contain these five columns (names are case-sensitive):

| Raw input column | Required content | Role |
|---|---|---|
| `OBJECTID` | Stable customer/meter identifier | Groups records by customer and keeps histories separate; **not** a detector feature |
| `timestamp` | Parseable timestamp, one-hour cadence per customer | Orders the history and generates calendar features |
| `normalized_building_energy_kwh` | Numeric, finite normalized energy reading | Consumption signal used to calculate the baseline and signal features |
| `latitude` | Numeric customer latitude | Retained for geographic localization; **not** a detector feature |
| `longitude` | Numeric customer longitude | Retained for geographic localization; **not** a detector feature |

The 30 engineered columns actually passed to the binary detector are listed below. They are calculated by `add_causal_features`; do not manufacture or pass these in place of the five raw columns:

**Baseline, residual, temporal and run features (15):**
`log_residual`, `relative_deviation`, `lag1_delta`, `lag24_delta`, `past_24h_cv`, `past_168h_cv`, `zero_streak`, `flatline_streak`, `hour_sin`, `hour_cos`, `weekday_sin`, `weekday_cos`, `month_sin`, `month_cos`, `is_weekend`.

**Trailing-window FFT features (7):**
`fft_dominant_frequency`, `fft_spectral_energy`, `fft_spectral_entropy`, `fft_spectral_centroid`, `fft_peak_magnitude`, `fft_low_band_energy`, `fft_high_band_energy`.

**Multi-scale Haar-wavelet features (8):**
`wavelet_energy_s1`, `wavelet_energy_s2`, `wavelet_energy_s3`, `wavelet_energy_s4`, `wavelet_coefficient_variance`, `wavelet_maximum_magnitude`, `wavelet_scale_entropy`, `wavelet_dominant_scale`.

For event-window characterization, the same raw signal/customer/time inputs produce the following 51 **post-detection** columns. These are used for event reports and deterministic type rules; they are not inputs to a learned type classifier:

`baseline_log`, `window_mean`, `window_std`, `window_median`, `window_variance`, `window_min`, `window_max`, `window_range`, `window_rms`, `window_skew`, `window_kurtosis`, `relative_mean`, `relative_std`, `relative_min`, `relative_max`, `relative_range`, `relative_slope`, `maximum_rate_change`, `pre_event_mean`, `post_event_mean`, `anomaly_duration_hours`, `recovery_hours`, `zero_fraction`, `max_zero_run`, `max_flatline_run`, `flatline_level_deviation`, `pre_event_cv`, `unique_fraction`, `dominant_frequency`, `spectral_energy`, `spectral_entropy`, `spectral_centroid`, `spectral_peak_magnitude`, `spectral_low_band_energy`, `spectral_high_band_energy`, `wavelet_energy_1`, `wavelet_energy_2`, `wavelet_energy_3`, `wavelet_energy_4`, `wavelet_coefficient_variance`, `wavelet_maximum_magnitude`, `wavelet_coefficient_entropy`, `wavelet_energy_ratio_1`, `wavelet_energy_ratio_2`, `wavelet_energy_ratio_3`, `wavelet_energy_ratio_4`, `wavelet_dominant_scale`, `hour_sin`, `hour_cos`, `weekday_sin`, `weekday_cos`.

The following source columns are **not** accepted or used as prediction inputs: `is_anomaly`, `anomaly_type`, `anomaly_event_id`, `event_scope`, `area_id`, `start_time`, `end_time`, `severity`, and `original_energy_kwh`. Source metadata such as building area/use type is also excluded.

The complete, copyable input and feature contract is in [`MODEL_INPUT_COLUMNS.txt`](./MODEL_INPUT_COLUMNS.txt); the notebook prints the same lists in its prediction-input section.

For event-window extraction and sequence merging after point detection:

```python
from gridvision_pipeline import predict_anomaly_events

events = predict_anomaly_events(
    incoming_customer_history,
    "models/anomaly_prediction/gridvision_anomaly_model.joblib",
)
```

This second stage merges adjacent alerts, extracts the available ±12-hour window around each detected event, computes the detailed time-domain/FFT/wavelet summaries, and assigns the final type using the deterministic rules. In streaming use, this characterization needs up to 12 hours of look-ahead; the point detector itself remains causal.

After an anomaly is detected, the rule-based event function can characterize its completed 25-hour signal window:

```python
from gridvision_pipeline import classify_event_window

event_result = classify_event_window(
    window_values=event_window_25_hours,
    pre_event_values=preceding_24_hours,
    timestamp=event_start,
    model_path="models/anomaly_prediction/gridvision_anomaly_model.joblib",
)
```

The function returns the rule-assigned anomaly type and extracted signal features. A complete centered window needs 12 hours after the event start; use `predict_point_anomalies` for causal hourly detection and the rule-based point label.

## Current held-out results

The saved report reflects the run with seed 42, 200/100/100 sampled customers, 150 training events per class, and 50 validation and test events per class:

| Metric | Validation | Held-out test |
|---|---:|---:|
| Point detection precision | 0.996 | 0.990 |
| Point detection recall | 0.999 | 0.990 |
| Point detection F1 | 0.998 | 0.990 |
| Point detection PR-AUC | 0.9997 | 0.9997 |
| Event detection precision / recall | 0.980 / 1.000 | 0.967 / 1.000 |
| Mean event detection delay (hours) | 0.005 | 0.025 |
| Rule-based event type macro-F1 | 1.000 | 1.000 |

The validation false-alert rate on clean rows was 0.003% (4 false alerts over 131,400 points); held-out test produced 0.11 false alerts per sampled customer. These results came from one controlled synthetic run with 50 test events per type. They demonstrate that the signal-feature binary detector can identify the injected templates; they are **not real-world performance estimates**. The rule-label score also measures only these deterministic synthetic patterns. Independent real anomaly labels are required before claiming operational detection quality.

## Recommended next steps before deployment

1. Evaluate on independently labeled, naturally occurring anomaly and outage events.
2. Tune event definitions, alert thresholds, window lengths, and false-alert budgets with domain owners using validation data only.
3. Validate temporal/event-level recall and detection delay, not just point metrics.
4. Add feeder/transformer/substation topology before claiming electrical asset localization.
5. Load the full customer population and evaluate season, geography, building type, and normalized-versus-raw energy calibration.
6. Add monitoring for missing intervals, schema changes, score drift, and customer-level false alerts.
