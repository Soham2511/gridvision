"""Leakage-aware GridVision anomaly detection and localization workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pywt
from scipy.stats import kurtosis, skew
from sklearn.cluster import DBSCAN
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    precision_recall_curve,
)
from gridvision_event_localization import (
    EventLocalizationConfig,
    evaluate_events,
    form_events,
    generate_event_summary,
    prepare_anomaly_records,
    visualize_events,
)


CUSTOMER = "OBJECTID"
TIMESTAMP = "timestamp"
ENERGY = "normalized_building_energy_kwh"
LATITUDE = "latitude"
LONGITUDE = "longitude"
INPUT_COLUMNS = [CUSTOMER, TIMESTAMP, ENERGY, LATITUDE, LONGITUDE]
ANOMALY_TYPES = ("spike", "drop", "zero_block", "flatline")
POINT_FEATURES = [
    "log_residual",
    "relative_deviation",
    "lag1_delta",
    "lag24_delta",
    "past_24h_cv",
    "past_168h_cv",
    "zero_streak",
    "flatline_streak",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
    "month_sin",
    "month_cos",
    "is_weekend",
    "fft_dominant_frequency",
    "fft_spectral_energy",
    "fft_spectral_entropy",
    "fft_spectral_centroid",
    "fft_peak_magnitude",
    "fft_low_band_energy",
    "fft_high_band_energy",
    "wavelet_energy_s1",
    "wavelet_energy_s2",
    "wavelet_energy_s3",
    "wavelet_energy_s4",
    "wavelet_coefficient_variance",
    "wavelet_maximum_magnitude",
    "wavelet_scale_entropy",
    "wavelet_dominant_scale",
]
EVENT_FEATURES = [
    "baseline_log",
    "window_mean",
    "window_std",
    "window_median",
    "window_variance",
    "window_min",
    "window_max",
    "window_range",
    "window_rms",
    "window_skew",
    "window_kurtosis",
    "relative_mean",
    "relative_std",
    "relative_min",
    "relative_max",
    "relative_range",
    "relative_slope",
    "maximum_rate_change",
    "pre_event_mean",
    "post_event_mean",
    "anomaly_duration_hours",
    "recovery_hours",
    "zero_fraction",
    "max_zero_run",
    "max_flatline_run",
    "flatline_level_deviation",
    "pre_event_cv",
    "unique_fraction",
    "dominant_frequency",
    "spectral_energy",
    "spectral_entropy",
    "spectral_centroid",
    "spectral_peak_magnitude",
    "spectral_low_band_energy",
    "spectral_high_band_energy",
    "wavelet_energy_1",
    "wavelet_energy_2",
    "wavelet_energy_3",
    "wavelet_energy_4",
    "wavelet_coefficient_variance",
    "wavelet_maximum_magnitude",
    "wavelet_coefficient_entropy",
    "wavelet_energy_ratio_1",
    "wavelet_energy_ratio_2",
    "wavelet_energy_ratio_3",
    "wavelet_energy_ratio_4",
    "wavelet_dominant_scale",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
]


@dataclass(frozen=True)
class PipelineConfig:
    parquet_path: str = "data/synthetic_2019_normal.parquet"
    gold_features_path: str | None = None
    model_path: str = "models/gridvision_anomaly_model.joblib"
    report_dir: str = "reports"
    random_seed: int = 42
    train_customer_sample: int = 200
    validation_customer_sample: int = 100
    test_customer_sample: int = 100
    training_score_sample: int = 200_000
    training_events_per_class: int = 150
    evaluation_events_per_class: int = 50
    false_positive_quantile: float = 0.995
    detector_negative_to_positive_ratio: int = 20
    minimum_zero_block_hours: int = 3
    minimum_flatline_hours: int = 6
    h3_resolution: int = 8
    spatial_radius_km: float = 5.0
    spatial_dbscan_min_customers: int = 2
    maximum_start_time_difference_minutes: int = 30
    minimum_temporal_overlap: float = 0.25
    maximum_interval_gap_minutes: int = 60


def inspect_parquet(path: str | Path) -> dict[str, Any]:
    """Validate the source schema and return a bounded profile."""
    parquet = pq.ParquetFile(path)
    names = set(parquet.schema.names)
    missing = set(INPUT_COLUMNS) - names
    if missing:
        raise ValueError(f"Parquet input is missing required columns: {sorted(missing)}")

    sample_columns = INPUT_COLUMNS + [
        column
        for column in ("is_anomaly", "anomaly_type", "original_energy_kwh")
        if column in names
    ]
    sample = parquet.read_row_group(0, columns=sample_columns).to_pandas()
    profile = {
        "path": str(path),
        "rows": parquet.metadata.num_rows,
        "row_groups": parquet.metadata.num_row_groups,
        "columns": parquet.schema.names,
        "sample_customers": int(sample[CUSTOMER].nunique()),
        "sample_time_min": str(sample[TIMESTAMP].min()),
        "sample_time_max": str(sample[TIMESTAMP].max()),
        "sample_energy_missing": int(sample[ENERGY].isna().sum()),
        "sample_energy_quantiles": sample[ENERGY].quantile(
            [0.0, 0.5, 0.99, 1.0]
        ).to_dict(),
    }
    if "is_anomaly" in sample:
        profile["source_anomaly_labels"] = (
            sample["is_anomaly"].value_counts(dropna=False).to_dict()
        )
        label_column_index = parquet.schema.names.index("is_anomaly")
        label_statistics = [
            parquet.metadata.row_group(group_index)
            .column(label_column_index)
            .statistics
            for group_index in range(parquet.metadata.num_row_groups)
        ]
        if all(
            statistics is not None and statistics.has_min_max
            for statistics in label_statistics
        ):
            null_counts = [statistics.null_count for statistics in label_statistics]
            profile["source_anomaly_label_metadata"] = {
                "minimum": min(statistics.min for statistics in label_statistics),
                "maximum": max(statistics.max for statistics in label_statistics),
                "null_count": (
                    int(sum(null_counts))
                    if all(count is not None for count in null_counts)
                    else None
                ),
                "row_groups_checked": int(len(label_statistics)),
            }
    return profile


def split_customers(
    path: str | Path, config: PipelineConfig
) -> tuple[dict[str, list[int]], dict[str, Any]]:
    """Split all customer IDs first, then sample each disjoint partition."""
    parquet = pq.ParquetFile(path)
    customer_id_set: set[int] = set()
    for batch in parquet.iter_batches(columns=[CUSTOMER], batch_size=250_000):
        customer_id_set.update(
            np.unique(batch.column(CUSTOMER).to_numpy()).astype(np.int64).tolist()
        )
    customer_ids = np.asarray(sorted(customer_id_set), dtype=np.int64)
    rng = np.random.default_rng(config.random_seed)
    shuffled = rng.permutation(customer_ids)
    train_end = int(len(shuffled) * 0.80)
    validation_end = int(len(shuffled) * 0.90)
    complete_partitions = {
        "train": shuffled[:train_end],
        "validation": shuffled[train_end:validation_end],
        "test": shuffled[validation_end:],
    }
    sample_sizes = {
        "train": config.train_customer_sample,
        "validation": config.validation_customer_sample,
        "test": config.test_customer_sample,
    }
    selected: dict[str, list[int]] = {}
    for name, ids in complete_partitions.items():
        count = min(sample_sizes[name], len(ids))
        selected[name] = sorted(
            rng.choice(ids, size=count, replace=False).astype(int).tolist()
        )
    if any(not selected[name] for name in selected):
        raise ValueError("Each split needs at least one sampled customer.")
    if (
        set(selected["train"]) & set(selected["validation"])
        or set(selected["train"]) & set(selected["test"])
        or set(selected["validation"]) & set(selected["test"])
    ):
        raise AssertionError("Customer partitions must be mutually exclusive.")
    integrity = {
        "source_customer_count": int(len(customer_ids)),
        "complete_customer_partitions": {
            key: int(len(ids)) for key, ids in complete_partitions.items()
        },
        "sampled_customer_partitions": {
            key: int(len(ids)) for key, ids in selected.items()
        },
        "customer_overlap": 0,
    }
    return selected, integrity


def load_customer_sample(
    path: str | Path, customer_splits: dict[str, list[int]]
) -> pd.DataFrame:
    """Read only model inputs and selected customers, one parquet row group at a time."""
    selected_ids = set().union(*(set(ids) for ids in customer_splits.values()))
    parquet = pq.ParquetFile(path)
    parts: list[pd.DataFrame] = []
    for batch in parquet.iter_batches(columns=INPUT_COLUMNS, batch_size=250_000):
        frame = batch.to_pandas()
        frame = frame.loc[frame[CUSTOMER].isin(selected_ids), INPUT_COLUMNS]
        if not frame.empty:
            parts.append(frame)
    if not parts:
        raise ValueError("No rows matched the selected customer IDs.")
    result = pd.concat(parts, ignore_index=True)
    result[CUSTOMER] = result[CUSTOMER].astype("int64")
    result[ENERGY] = pd.to_numeric(result[ENERGY], errors="coerce").astype("float32")
    result[TIMESTAMP] = pd.to_datetime(result[TIMESTAMP], errors="coerce")
    missing = result[INPUT_COLUMNS].isna().sum()
    if missing.any():
        missing_counts = {key: int(value) for key, value in missing.items() if value}
        raise ValueError(
            "Selected records contain missing required values; resolve these "
            f"before modeling: {missing_counts}"
        )
    result = result.sort_values([CUSTOMER, TIMESTAMP], kind="mergesort").reset_index(
        drop=True
    )
    duplicate_count = int(result.duplicated([CUSTOMER, TIMESTAMP]).sum())
    if duplicate_count:
        raise ValueError(f"Found {duplicate_count} duplicate customer-hour records.")
    time_deltas = result.groupby(CUSTOMER, sort=False)[TIMESTAMP].diff()
    irregular_intervals = time_deltas.notna() & time_deltas.ne(pd.Timedelta(hours=1))
    if irregular_intervals.any():
        examples = result.loc[
            irregular_intervals, [CUSTOMER, TIMESTAMP]
        ].head(5).to_dict("records")
        raise ValueError(
            "Selected customers must have contiguous hourly observations for "
            f"rolling features; found irregular intervals, examples: {examples}"
        )
    return result


def temporal_boundaries(data: pd.DataFrame) -> dict[str, pd.Timestamp]:
    """Compute global chronological 70/15/15 boundaries without model fitting."""
    start = data[TIMESTAMP].min()
    stop = data[TIMESTAMP].max() + pd.Timedelta(hours=1)
    duration = stop - start
    return {
        "start": start,
        "train_end": start + duration * 0.70,
        "validation_end": start + duration * 0.85,
        "stop": stop,
    }


def add_causal_features(data: pd.DataFrame) -> pd.DataFrame:
    """Create point features using current and strictly prior customer readings."""
    if data.empty:
        raise ValueError("Cannot engineer features from an empty frame.")
    frames: list[pd.DataFrame] = []
    for _, group in data.groupby(CUSTOMER, sort=False, observed=True):
        group = group.sort_values(TIMESTAMP, kind="mergesort").copy()
        energy = group[ENERGY].astype("float64").clip(lower=0)
        history = energy.shift(1)
        rolling_24 = history.rolling(24, min_periods=12).median()
        rolling_168 = history.rolling(168, min_periods=48).median()
        baseline = rolling_168.fillna(rolling_24).fillna(
            history.expanding(min_periods=1).median()
        )
        baseline = baseline.fillna(energy).clip(lower=1e-4)

        log_energy = np.log1p(energy)
        log_baseline = np.log1p(baseline)
        unchanged = energy.diff().abs().le(1e-6).fillna(False).astype(np.int8)
        zero = energy.le(1e-4).astype(np.int8)
        flatline_streak = unchanged.groupby((unchanged == 0).cumsum()).cumsum()
        zero_streak = zero.groupby((zero == 0).cumsum()).cumsum()
        timestamp = group[TIMESTAMP]
        hour = timestamp.dt.hour.to_numpy()
        weekday = timestamp.dt.dayofweek.to_numpy()
        month = timestamp.dt.month.to_numpy() - 1
        residual_signal = (log_energy - log_baseline).to_numpy(dtype=np.float64)
        fft_windows = np.lib.stride_tricks.sliding_window_view(
            np.pad(residual_signal, (24, 0), mode="edge"), 25
        )
        centered_windows = fft_windows - fft_windows.mean(axis=1, keepdims=True)
        fft_magnitude = np.abs(np.fft.rfft(centered_windows, axis=1))
        fft_power = np.square(fft_magnitude[:, 1:])
        fft_frequencies = np.fft.rfftfreq(25, d=1.0)[1:]
        fft_total_power = fft_power.sum(axis=1)
        fft_probabilities = fft_power / (fft_total_power[:, None] + 1e-12)
        wavelet_details: list[np.ndarray] = []
        wavelet_energies: list[np.ndarray] = []
        for scale in (1, 2, 4, 8):
            lagged = pd.Series(residual_signal).shift(scale).fillna(0).to_numpy()
            detail = (residual_signal - lagged) / np.sqrt(2.0)
            wavelet_details.append(detail)
            wavelet_energies.append(
                pd.Series(np.square(detail))
                .rolling(25, min_periods=1)
                .mean()
                .to_numpy()
            )
        wavelet_energy_matrix = np.column_stack(wavelet_energies)
        wavelet_energy_total = wavelet_energy_matrix.sum(axis=1)
        wavelet_scale_probabilities = wavelet_energy_matrix / (
            wavelet_energy_total[:, None] + 1e-12
        )
        wavelet_details_matrix = np.column_stack(wavelet_details)
        features = pd.DataFrame(
            {
                CUSTOMER: group[CUSTOMER].to_numpy(),
                TIMESTAMP: timestamp.to_numpy(),
                LATITUDE: group[LATITUDE].to_numpy(dtype=np.float64),
                LONGITUDE: group[LONGITUDE].to_numpy(dtype=np.float64),
                ENERGY: energy.to_numpy(dtype=np.float32),
                "baseline": baseline.to_numpy(dtype=np.float32),
                "log_residual": (log_energy - log_baseline).to_numpy(
                    dtype=np.float32
                ),
                "relative_deviation": (
                    (energy - baseline) / (baseline + 0.01)
                ).clip(-10, 20).to_numpy(dtype=np.float32),
                "lag1_delta": (log_energy - np.log1p(history.clip(lower=0))).to_numpy(
                    dtype=np.float32
                ),
                "lag24_delta": (
                    log_energy - np.log1p(energy.shift(24).clip(lower=0))
                ).to_numpy(dtype=np.float32),
                "past_24h_cv": (
                    history.rolling(24, min_periods=12).std() / (baseline + 0.01)
                )
                .fillna(0)
                .clip(0, 20)
                .to_numpy(dtype=np.float32),
                "past_168h_cv": (
                    history.rolling(168, min_periods=48).std() / (baseline + 0.01)
                )
                .fillna(0)
                .clip(0, 20)
                .to_numpy(dtype=np.float32),
                "zero_streak": zero_streak.to_numpy(dtype=np.float32),
                "flatline_streak": flatline_streak.to_numpy(dtype=np.float32),
                "hour_sin": np.sin(2 * np.pi * hour / 24).astype(np.float32),
                "hour_cos": np.cos(2 * np.pi * hour / 24).astype(np.float32),
                "weekday_sin": np.sin(2 * np.pi * weekday / 7).astype(np.float32),
                "weekday_cos": np.cos(2 * np.pi * weekday / 7).astype(np.float32),
                "month_sin": np.sin(2 * np.pi * month / 12).astype(np.float32),
                "month_cos": np.cos(2 * np.pi * month / 12).astype(np.float32),
                "is_weekend": (weekday >= 5).astype(np.float32),
                "fft_dominant_frequency": fft_frequencies[
                    np.argmax(fft_power, axis=1)
                ].astype(np.float32),
                "fft_spectral_energy": np.log1p(fft_total_power).astype(np.float32),
                "fft_spectral_entropy": (
                    -np.sum(
                        fft_probabilities * np.log(fft_probabilities + 1e-12),
                        axis=1,
                    )
                    / np.log(max(fft_probabilities.shape[1], 2))
                ).astype(np.float32),
                "fft_spectral_centroid": (
                    np.sum(fft_power * fft_frequencies[None, :], axis=1)
                    / (fft_total_power + 1e-12)
                ).astype(np.float32),
                "fft_peak_magnitude": np.log1p(
                    fft_magnitude[:, 1:].max(axis=1)
                ).astype(np.float32),
                "fft_low_band_energy": np.log1p(
                    fft_power[:, fft_frequencies <= (1 / 6)].sum(axis=1)
                ).astype(np.float32),
                "fft_high_band_energy": np.log1p(
                    fft_power[:, fft_frequencies > (1 / 6)].sum(axis=1)
                ).astype(np.float32),
                "wavelet_energy_s1": np.log1p(wavelet_energy_matrix[:, 0]).astype(
                    np.float32
                ),
                "wavelet_energy_s2": np.log1p(wavelet_energy_matrix[:, 1]).astype(
                    np.float32
                ),
                "wavelet_energy_s3": np.log1p(wavelet_energy_matrix[:, 2]).astype(
                    np.float32
                ),
                "wavelet_energy_s4": np.log1p(wavelet_energy_matrix[:, 3]).astype(
                    np.float32
                ),
                "wavelet_coefficient_variance": wavelet_details_matrix.var(
                    axis=1
                ).astype(np.float32),
                "wavelet_maximum_magnitude": np.abs(
                    wavelet_details_matrix
                ).max(axis=1).astype(np.float32),
                "wavelet_scale_entropy": (
                    -np.sum(
                        wavelet_scale_probabilities
                        * np.log(wavelet_scale_probabilities + 1e-12),
                        axis=1,
                    )
                    / np.log(4)
                ).astype(np.float32),
                "wavelet_dominant_scale": (
                    np.argmax(wavelet_energy_matrix, axis=1) + 1
                ).astype(np.float32),
            }
        )
        frames.append(features)
    result = pd.concat(frames, ignore_index=True)
    result[POINT_FEATURES] = result[POINT_FEATURES].replace(
        [np.inf, -np.inf], np.nan
    )
    result[POINT_FEATURES] = result[POINT_FEATURES].fillna(0)
    return result.sort_values([CUSTOMER, TIMESTAMP], kind="mergesort").reset_index(
        drop=True
    )


def fit_detector(
    train_features: pd.DataFrame,
    labels: np.ndarray,
    config: PipelineConfig,
) -> tuple[RandomForestClassifier, float, dict[str, Any]]:
    """Fit a binary detector on injected positives and sampled normal training points."""
    if train_features.empty:
        raise ValueError("Training feature set is empty.")
    rng = np.random.default_rng(config.random_seed)
    positive_positions = np.flatnonzero(labels == 1)
    negative_positions = np.flatnonzero(labels == 0)
    if not len(positive_positions) or not len(negative_positions):
        raise ValueError("Training detector requires both normal and injected points.")
    negative_count = min(
        len(negative_positions),
        max(
            config.training_score_sample,
            len(positive_positions) * config.detector_negative_to_positive_ratio,
        ),
    )
    sampled_negative_positions = rng.choice(
        negative_positions, size=negative_count, replace=False
    )
    sample_positions = np.concatenate(
        [positive_positions, sampled_negative_positions]
    )
    train_matrix = train_features.iloc[sample_positions][POINT_FEATURES].to_numpy(
        dtype=np.float32
    )
    train_labels = labels[sample_positions]
    detector = RandomForestClassifier(
        n_estimators=300,
        max_features="sqrt",
        min_samples_leaf=2,
        max_depth=16,
        class_weight="balanced_subsample",
        random_state=config.random_seed,
        n_jobs=-1,
    )
    detector.fit(train_matrix, train_labels)
    train_scores = detector.predict_proba(train_matrix)[:, 1]
    threshold = float(np.quantile(train_scores, config.false_positive_quantile))
    metadata = {
        "train_rows": int(len(train_features)),
        "detector_fit_rows": int(len(sample_positions)),
        "detector_positive_fit_rows": int(len(positive_positions)),
        "detector_normal_fit_rows": int(negative_count),
        "threshold_quantile": config.false_positive_quantile,
        "threshold": threshold,
        "detector_type": "binary RandomForest trained on synthetic events + normal data",
    }
    return detector, threshold, metadata


def _event_features(
    values: np.ndarray,
    baseline_values: np.ndarray,
    timestamp: pd.Timestamp,
    event_offset: int | None = None,
) -> dict[str, float]:
    baseline = float(np.nanmedian(baseline_values))
    baseline = max(baseline, 1e-4)
    window = np.asarray(values, dtype=np.float64)
    if window.ndim != 1 or not len(window):
        raise ValueError("An event signal window must contain hourly readings.")
    event_offset = len(window) // 2 if event_offset is None else event_offset
    if not 0 <= event_offset < len(window):
        raise ValueError("event_offset must identify a reading inside the window.")
    log_window = np.log1p(np.clip(window, 0, None))
    relative = (window - baseline) / (baseline + 0.01)
    centered = relative - np.mean(relative)
    spectrum = np.abs(np.fft.rfft(centered)) ** 2
    frequencies = np.fft.rfftfreq(len(centered), d=1.0)
    if len(spectrum) > 1:
        spectral = spectrum[1:]
        spectral_freq = frequencies[1:]
        total_spectral = float(spectral.sum())
        normalized = spectral / (total_spectral + 1e-12)
        dominant_frequency = float(spectral_freq[int(np.argmax(spectral))])
        spectral_entropy = float(
            -np.sum(normalized * np.log(normalized + 1e-12))
            / np.log(max(len(normalized), 2))
        )
        spectral_centroid = float(
            np.sum(spectral_freq * spectral) / (total_spectral + 1e-12)
        )
        peak_magnitude = float(np.sqrt(np.max(spectral)))
        low_band_energy = float(spectral[spectral_freq <= (1 / 6)].sum())
        high_band_energy = float(spectral[spectral_freq > (1 / 6)].sum())
    else:
        (
            total_spectral,
            dominant_frequency,
            spectral_entropy,
            spectral_centroid,
            peak_magnitude,
            low_band_energy,
            high_band_energy,
        ) = (0.0,) * 7
    wavelet_level = min(4, pywt.dwt_max_level(len(centered), pywt.Wavelet("haar").dec_len))
    coefficients = pywt.wavedec(
        centered, "haar", level=wavelet_level, mode="symmetric"
    )
    detail_coefficients = [
        coefficients[-level] if level <= wavelet_level else np.zeros(1)
        for level in range(1, 5)
    ]
    wavelet_energies = np.asarray(
        [float(np.mean(np.square(detail))) for detail in detail_coefficients]
    )
    wavelet_probabilities = wavelet_energies / (wavelet_energies.sum() + 1e-12)
    all_details = np.concatenate(detail_coefficients)
    coefficient_probabilities = np.square(all_details)
    coefficient_probabilities /= coefficient_probabilities.sum() + 1e-12
    coefficient_entropy = float(
        -np.sum(coefficient_probabilities * np.log(coefficient_probabilities + 1e-12))
        / np.log(max(len(coefficient_probabilities), 2))
    )
    slope = (
        float(np.polyfit(np.arange(len(relative)), relative, deg=1)[0])
        if len(relative) > 1
        else 0.0
    )
    zero_mask = window <= 1e-4
    flat_mask = np.abs(np.diff(window, prepend=window[0])) <= max(
        1e-6, baseline * 1e-4
    )
    flat_mask[0] = False
    flat_mask[:event_offset] = False
    change_mask = np.abs(relative) >= 0.5
    post_recovery = np.flatnonzero(
        (np.arange(len(relative)) >= event_offset) & (np.abs(relative) <= 0.2)
    )
    recovery_hours = (
        float(post_recovery[0] - event_offset) if len(post_recovery) else 12.0
    )

    def max_true_run(mask: np.ndarray) -> tuple[int, int, int]:
        groups = np.diff(np.r_[False, mask, False].astype(np.int8))
        starts = np.flatnonzero(groups == 1)
        ends = np.flatnonzero(groups == -1)
        if not len(starts):
            return 0, 0, 0
        longest = int(np.argmax(ends - starts))
        return int(ends[longest] - starts[longest]), int(starts[longest]), int(ends[longest])

    max_flat_run, flat_start, flat_end = max_true_run(flat_mask)
    flatline_level_deviation = (
        abs(float(np.mean(window[flat_start:flat_end])) - baseline) / (baseline + 0.01)
        if max_flat_run
        else 0.0
    )

    return {
        "baseline_log": float(np.log1p(baseline)),
        "window_mean": float(np.mean(log_window)),
        "window_std": float(np.std(log_window)),
        "window_median": float(np.median(log_window)),
        "window_variance": float(np.var(log_window)),
        "window_min": float(np.min(log_window)),
        "window_max": float(np.max(log_window)),
        "window_range": float(np.ptp(log_window)),
        "window_rms": float(np.sqrt(np.mean(np.square(log_window)))),
        "window_skew": (
            float(skew(log_window, bias=False))
            if len(window) > 2 and np.std(log_window) > 1e-12
            else 0.0
        ),
        "window_kurtosis": (
            float(kurtosis(log_window, bias=False))
            if len(window) > 3 and np.std(log_window) > 1e-12
            else 0.0
        ),
        "relative_mean": float(np.mean(relative)),
        "relative_std": float(np.std(relative)),
        "relative_min": float(np.min(relative)),
        "relative_max": float(np.max(relative)),
        "relative_range": float(np.ptp(relative)),
        "relative_slope": slope,
        "maximum_rate_change": (
            float(np.max(np.abs(np.diff(relative)))) if len(relative) > 1 else 0.0
        ),
        "pre_event_mean": float(np.mean(log_window[:event_offset]))
        if event_offset
        else float(log_window[event_offset]),
        "post_event_mean": float(np.mean(log_window[event_offset + 1 :]))
        if event_offset + 1 < len(log_window)
        else float(log_window[event_offset]),
        "anomaly_duration_hours": float(np.sum(change_mask)),
        "recovery_hours": recovery_hours,
        "zero_fraction": float(np.mean(window <= 1e-4)),
        "max_zero_run": float(max_true_run(zero_mask)[0]),
        "max_flatline_run": float(max_flat_run),
        "flatline_level_deviation": flatline_level_deviation,
        "pre_event_cv": float(np.std(baseline_values) / (baseline + 0.01)),
        "unique_fraction": float(len(np.unique(np.round(window, 5))) / len(window)),
        "dominant_frequency": dominant_frequency,
        "spectral_energy": float(np.log1p(total_spectral)),
        "spectral_entropy": spectral_entropy,
        "spectral_centroid": spectral_centroid,
        "spectral_peak_magnitude": float(np.log1p(peak_magnitude)),
        "spectral_low_band_energy": float(np.log1p(low_band_energy)),
        "spectral_high_band_energy": float(np.log1p(high_band_energy)),
        "wavelet_energy_1": float(np.log1p(wavelet_energies[0])),
        "wavelet_energy_2": float(np.log1p(wavelet_energies[1])),
        "wavelet_energy_3": float(np.log1p(wavelet_energies[2])),
        "wavelet_energy_4": float(np.log1p(wavelet_energies[3])),
        "wavelet_coefficient_variance": float(np.var(all_details)),
        "wavelet_maximum_magnitude": float(np.max(np.abs(all_details))),
        "wavelet_coefficient_entropy": coefficient_entropy,
        "wavelet_energy_ratio_1": float(wavelet_probabilities[0]),
        "wavelet_energy_ratio_2": float(wavelet_probabilities[1]),
        "wavelet_energy_ratio_3": float(wavelet_probabilities[2]),
        "wavelet_energy_ratio_4": float(wavelet_probabilities[3]),
        "wavelet_dominant_scale": float(np.argmax(wavelet_energies) + 1),
        "hour_sin": float(np.sin(2 * np.pi * timestamp.hour / 24)),
        "hour_cos": float(np.cos(2 * np.pi * timestamp.hour / 24)),
        "weekday_sin": float(np.sin(2 * np.pi * timestamp.dayofweek / 7)),
        "weekday_cos": float(np.cos(2 * np.pi * timestamp.dayofweek / 7)),
    }


def generate_synthetic_events(
    data: pd.DataFrame,
    start: pd.Timestamp,
    stop: pd.Timestamp,
    events_per_class: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Inject controlled event windows into a copy of one split, never into source data."""
    if events_per_class < 1:
        raise ValueError("events_per_class must be positive.")
    rng = np.random.default_rng(seed)
    working = data.copy()
    working = working.sort_values([CUSTOMER, TIMESTAMP], kind="mergesort").reset_index(
        drop=True
    )
    energy_arrays: dict[int, np.ndarray] = {}
    timestamp_arrays: dict[int, np.ndarray] = {}
    positions: dict[int, np.ndarray] = {}
    for customer, group in working.groupby(CUSTOMER, sort=False):
        row_positions = group.index.to_numpy()
        cid = int(customer)
        positions[cid] = row_positions
        energy_arrays[cid] = working.loc[row_positions, ENERGY].to_numpy(
            dtype=np.float64, copy=True
        )
        timestamp_arrays[cid] = pd.to_datetime(
            working.loc[row_positions, TIMESTAMP]
        ).to_numpy()

    events: list[dict[str, Any]] = []
    point_labels = np.zeros(len(working), dtype=np.uint8)
    used_windows: dict[int, list[tuple[int, int]]] = {
        customer: [] for customer in positions
    }
    durations = {"spike": 1, "drop": 6, "zero_block": 6, "flatline": 8}
    customer_ids = np.array(list(positions))
    for anomaly_type in ANOMALY_TYPES:
        made = 0
        attempts = 0
        while made < events_per_class and attempts < events_per_class * 100:
            attempts += 1
            customer = int(rng.choice(customer_ids))
            customer_times = pd.to_datetime(timestamp_arrays[customer])
            valid = np.flatnonzero(
                (customer_times >= start) & (customer_times < stop)
            )
            valid = valid[
                (valid >= 24) & (valid + durations[anomaly_type] + 12 < len(customer_times))
            ]
            if not len(valid):
                continue
            event_start = int(rng.choice(valid))
            event_end = event_start + durations[anomaly_type]
            if any(
                event_start - 12 < old_end + 12 and event_end + 12 > old_start - 12
                for old_start, old_end in used_windows[customer]
            ):
                continue

            signal = energy_arrays[customer]
            pre = signal[max(0, event_start - 24) : event_start]
            baseline = max(float(np.median(pre)), 1e-4)
            original_segment = signal[event_start:event_end].copy()
            if anomaly_type == "spike":
                signal[event_start] = max(
                    baseline * 20,
                    float(signal[event_start]) * 10,
                    baseline + 5,
                )
            elif anomaly_type == "drop":
                signal[event_start:event_end] = max(baseline * 0.02, 0.001)
            elif anomaly_type == "zero_block":
                signal[event_start:event_end] = 0.0
            else:
                flat_value = float(signal[event_start - 1])
                signal[event_start:event_end] = flat_value
            if np.array_equal(signal[event_start:event_end], original_segment):
                continue

            start_time = pd.Timestamp(customer_times[event_start])
            stop_time = pd.Timestamp(customer_times[event_end - 1]) + pd.Timedelta(
                hours=1
            )
            relative_start = max(0, event_start - 12)
            relative_stop = min(len(signal), event_start + 13)
            values = signal[relative_start:relative_stop]
            # Keep feature windows fixed-width; edge events are rejected by candidate filtering.
            if len(values) != 25:
                continue
            event_features = _event_features(values, pre, start_time)
            row_positions = positions[customer]
            lat = float(working.loc[row_positions[event_start], LATITUDE])
            lon = float(working.loc[row_positions[event_start], LONGITUDE])
            event_id = f"{anomaly_type}_{made:05d}"
            events.append(
                {
                    **event_features,
                    "event_id": event_id,
                    "anomaly_type": anomaly_type,
                    CUSTOMER: customer,
                    TIMESTAMP: start_time,
                    "end_time": stop_time,
                    LATITUDE: lat,
                    LONGITUDE: lon,
                }
            )
            point_labels[row_positions[event_start:event_end]] = 1
            used_windows[customer].append((event_start, event_end))
            made += 1
        if made < events_per_class:
            raise RuntimeError(
                f"Could only generate {made}/{events_per_class} {anomaly_type} "
                f"events in the requested time window."
            )

    for customer, values in energy_arrays.items():
        working.loc[positions[customer], ENERGY] = values.astype(np.float32)
    working["injected_anomaly"] = point_labels
    event_frame = pd.DataFrame(events)
    return working, event_frame, event_frame["anomaly_type"].value_counts().to_dict()


def learn_rule_thresholds(
    normal_training_features: pd.DataFrame,
    config: PipelineConfig,
) -> dict[str, float]:
    """Learn spike/drop cutoffs from normal training residual behavior."""
    relative = normal_training_features["relative_deviation"].to_numpy()
    return {
        "spike_relative_deviation": float(np.quantile(relative, 0.999)),
        "drop_relative_deviation": float(np.quantile(relative, 0.001)),
        "zero_block_minimum_hours": float(config.minimum_zero_block_hours),
        "flatline_minimum_hours": float(config.minimum_flatline_hours),
        "flatline_minimum_pre_event_cv": 0.05,
        "flatline_minimum_level_deviation": 0.001,
    }


def classify_anomaly_type(
    event_features: dict[str, float] | pd.Series,
    thresholds: dict[str, float],
) -> str:
    """Apply interpretable signal rules after a point/event was detected."""
    values = event_features
    if (
        values["max_zero_run"] >= thresholds["zero_block_minimum_hours"]
        and np.expm1(values["baseline_log"]) > 0.01
    ):
        return "zero_block"
    if (
        values["max_flatline_run"] >= thresholds["flatline_minimum_hours"]
        and values["pre_event_cv"] >= thresholds["flatline_minimum_pre_event_cv"]
        and values["flatline_level_deviation"]
        >= thresholds["flatline_minimum_level_deviation"]
    ):
        return "flatline"
    if values["relative_max"] >= thresholds["spike_relative_deviation"]:
        return "spike"
    if values["relative_min"] <= thresholds["drop_relative_deviation"]:
        return "drop"
    return "spike" if values["relative_mean"] >= 0 else "drop"


def classify_point_anomaly(
    point_features: dict[str, float] | pd.Series,
    thresholds: dict[str, float],
) -> str:
    """Assign a detected point to a rule-based anomaly category."""
    if (
        point_features["zero_streak"] >= thresholds["zero_block_minimum_hours"]
        and point_features["baseline"] > 0.01
    ):
        return "zero_block"
    if (
        point_features["flatline_streak"] >= thresholds["flatline_minimum_hours"]
        and point_features["past_24h_cv"]
        >= thresholds["flatline_minimum_pre_event_cv"]
        and abs(point_features["relative_deviation"])
        >= thresholds["flatline_minimum_level_deviation"]
    ):
        return "flatline"
    deviation = point_features["relative_deviation"]
    if deviation >= thresholds["spike_relative_deviation"]:
        return "spike"
    if deviation <= thresholds["drop_relative_deviation"]:
        return "drop"
    return "spike" if deviation >= 0 else "drop"


def evaluate_detection(
    detector: RandomForestClassifier,
    threshold: float,
    test_features: pd.DataFrame,
    labels: np.ndarray,
    rule_thresholds: dict[str, float],
    event_truth: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Score only the test portion and report rare-event-aware metrics."""
    scores = detector.predict_proba(
        test_features[POINT_FEATURES].to_numpy(dtype=np.float32)
    )[:, 1]
    predictions = scores >= threshold
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, predictions, average="binary", zero_division=0
    )
    metrics = {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "pr_auc": float(average_precision_score(labels, scores)),
        "false_alerts_per_customer": float(
            ((predictions) & (labels == 0)).sum()
            / max(test_features[CUSTOMER].nunique(), 1)
        ),
        "threshold": float(threshold),
        "test_points": int(len(labels)),
        "positive_points": int(np.sum(labels)),
    }
    scored = test_features[[CUSTOMER, TIMESTAMP, LATITUDE, LONGITUDE]].copy()
    scored["anomaly_score"] = scores
    scored["is_detected"] = predictions
    scored["is_injected_anomaly"] = labels.astype(bool)
    scored["anomaly_type"] = [
        classify_point_anomaly(row, rule_thresholds) if detected else None
        for row, detected in zip(
            test_features.to_dict(orient="records"), predictions
        )
    ]
    detected_intervals: dict[int, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    detected_event_count = 0
    detected_delays: list[float] = []
    for event in event_truth.itertuples(index=False):
        customer = int(getattr(event, CUSTOMER))
        event_start = pd.Timestamp(getattr(event, TIMESTAMP))
        event_end = pd.Timestamp(event.end_time)
        detected_intervals.setdefault(customer, []).append((event_start, event_end))
        event_points = scored.loc[
            (scored[CUSTOMER] == customer)
            & (scored[TIMESTAMP] >= event_start)
            & (scored[TIMESTAMP] < event_end)
            & scored["is_detected"]
        ]
        if not event_points.empty:
            detected_event_count += 1
            delay = (
                pd.Timestamp(event_points[TIMESTAMP].min()) - event_start
            ).total_seconds() / 3600
            detected_delays.append(float(delay))

    predicted_bursts = 0
    matched_bursts = 0
    detected_rows = scored.loc[scored["is_detected"]]
    for customer, group in detected_rows.groupby(CUSTOMER, sort=False):
        times = pd.to_datetime(group[TIMESTAMP]).sort_values().to_numpy()
        if not len(times):
            continue
        starts = np.r_[0, np.flatnonzero(np.diff(times) > np.timedelta64(1, "h")) + 1]
        ends = np.r_[starts[1:], len(times)]
        for burst_start, burst_end in zip(starts, ends):
            predicted_bursts += 1
            burst_times = pd.to_datetime(times[burst_start:burst_end])
            if any(
                (burst_times >= event_start).any()
                and (burst_times < event_end).any()
                for event_start, event_end in detected_intervals.get(int(customer), [])
            ):
                matched_bursts += 1
    metrics["event_recall"] = float(
        detected_event_count / max(len(event_truth), 1)
    )
    metrics["event_precision"] = float(
        matched_bursts / max(predicted_bursts, 1)
    )
    metrics["event_detection_delay_hours"] = (
        float(np.mean(detected_delays)) if detected_delays else None
    )
    metrics["ground_truth_events"] = int(len(event_truth))
    metrics["predicted_event_bursts"] = int(predicted_bursts)
    return metrics, scored


def evaluate_rule_classification(
    event_features: pd.DataFrame,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    """Evaluate deterministic anomaly-type rules against held-out synthetic events."""
    truth = event_features["anomaly_type"]
    predicted = [
        classify_anomaly_type(row, thresholds)
        for row in event_features.to_dict(orient="records")
    ]
    return {
        "macro_f1": float(f1_score(truth, predicted, average="macro")),
        "classification_report": classification_report(
            truth, predicted, labels=list(ANOMALY_TYPES), output_dict=True, zero_division=0
        ),
        "confusion_matrix": confusion_matrix(
            truth, predicted, labels=list(ANOMALY_TYPES)
        ).tolist(),
        "class_order": list(ANOMALY_TYPES),
        "event_count": int(len(truth)),
    }


def localize_geographic_clusters(
    scored_points: pd.DataFrame,
    radius_km: float = 5.0,
    minimum_customers: int = 2,
) -> pd.DataFrame:
    """Cluster simultaneous detected coordinates; clusters are not grid asset boundaries."""
    points = scored_points.loc[scored_points["is_detected"]].copy()
    points["event_hour"] = pd.to_datetime(points[TIMESTAMP]).dt.floor("h")
    points["geographic_cluster"] = -1
    eps_radians = radius_km / 6371.0088
    for _, indices in points.groupby("event_hour", sort=False).groups.items():
        if len(indices) < minimum_customers:
            continue
        coordinates = np.radians(points.loc[indices, [LATITUDE, LONGITUDE]].to_numpy())
        labels = DBSCAN(
            eps=eps_radians,
            min_samples=minimum_customers,
            metric="haversine",
            algorithm="ball_tree",
        ).fit_predict(coordinates)
        points.loc[indices, "geographic_cluster"] = labels
    return points


def save_model_bundle(
    model_path: str | Path,
    detector: RandomForestClassifier,
    threshold: float,
    rule_thresholds: dict[str, float],
    config: PipelineConfig,
    detector_metadata: dict[str, Any],
    metrics: dict[str, Any],
) -> Path:
    """Persist fitted estimators, feature contract, thresholds, and provenance."""
    path = Path(model_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "detector": detector,
        "detector_threshold": threshold,
        "rule_thresholds": rule_thresholds,
        "point_features": POINT_FEATURES,
        "event_features": EVENT_FEATURES,
        "anomaly_types": list(ANOMALY_TYPES),
        "detection_feature_groups": {
            "time_domain_and_baseline": [
                feature
                for feature in POINT_FEATURES
                if not feature.startswith(("fft_", "wavelet_"))
            ],
            "fft": [feature for feature in POINT_FEATURES if feature.startswith("fft_")],
            "wavelet": [
                feature for feature in POINT_FEATURES if feature.startswith("wavelet_")
            ],
        },
        "training_metadata": detector_metadata,
        "evaluation_metrics": metrics,
        "config": asdict(config),
        "source_columns_used": INPUT_COLUMNS,
        "source_columns_excluded": [
            "is_anomaly",
            "anomaly_type",
            "anomaly_event_id",
            "event_scope",
            "area_id",
            "start_time",
            "end_time",
            "severity",
            "original_energy_kwh",
        ],
        "localization_note": (
            "DBSCAN groups are geographic clusters only; feeder/transformer IDs "
            "were not supplied."
        ),
    }
    joblib.dump(bundle, path, compress=3)
    return path


def load_model_bundle(model_path: str | Path) -> dict[str, Any]:
    """Load and validate the persisted GridVision inference bundle."""
    bundle = joblib.load(model_path)
    required = {
        "detector",
        "detector_threshold",
        "rule_thresholds",
        "point_features",
    }
    missing = required - set(bundle)
    if missing:
        raise ValueError(f"Model bundle is missing required fields: {sorted(missing)}")
    if not np.isfinite(bundle["detector_threshold"]):
        raise ValueError("Model bundle has a non-finite detector threshold.")
    if not bundle["point_features"] or not set(bundle["point_features"]).issubset(
        POINT_FEATURES
    ):
        raise ValueError("Model bundle has an incompatible point-feature contract.")
    return bundle


def predict_point_anomalies(
    data: pd.DataFrame, model_path: str | Path
) -> pd.DataFrame:
    """Load a saved bundle and score new customer-hour records."""
    bundle = load_model_bundle(model_path)
    features = add_causal_features(data)
    scores = bundle["detector"].predict_proba(
        features[bundle["point_features"]].to_numpy(dtype=np.float32)
    )[:, 1]
    results = features[[CUSTOMER, TIMESTAMP, LATITUDE, LONGITUDE, ENERGY]].copy()
    results["anomaly_score"] = scores
    results["is_anomaly"] = scores >= bundle["detector_threshold"]
    results["anomaly_type"] = [
        classify_point_anomaly(row, bundle["rule_thresholds"])
        if detected
        else None
        for row, detected in zip(features.to_dict(orient="records"), results["is_anomaly"])
    ]
    return results


def predict_anomaly_events(
    data: pd.DataFrame,
    model_path: str | Path,
    merge_gap_hours: int = 1,
) -> pd.DataFrame:
    """Detect causal points, merge adjacent alerts, extract windows, and apply type rules."""
    bundle = load_model_bundle(model_path)
    return predict_anomaly_events_from_bundle(data, bundle, merge_gap_hours)


def predict_anomaly_events_from_bundle(
    data: pd.DataFrame,
    bundle: dict[str, Any],
    merge_gap_hours: int = 1,
) -> pd.DataFrame:
    """Run the saved bundle's event prediction without reloading it."""
    return _predict_anomaly_events_from_bundle(data, bundle, merge_gap_hours)


def _predict_anomaly_events_from_bundle(
    data: pd.DataFrame,
    bundle: dict[str, Any],
    merge_gap_hours: int = 1,
) -> pd.DataFrame:
    """Run the existing event-window predictor using an already loaded model bundle."""
    if "detector" not in bundle or "rule_thresholds" not in bundle:
        raise ValueError("Model bundle is missing the detector or rule thresholds.")
    if "detector_threshold" not in bundle or "point_features" not in bundle:
        raise ValueError("Model bundle is missing the point threshold or feature contract.")
    if merge_gap_hours < 0:
        raise ValueError("merge_gap_hours must be non-negative.")
    features = add_causal_features(data)
    scores = bundle["detector"].predict_proba(
        features[bundle["point_features"]].to_numpy(dtype=np.float32)
    )[:, 1]
    predicted = scores >= bundle["detector_threshold"]
    feature_rows = features.assign(anomaly_score=scores, is_detected=predicted)
    event_rows: list[dict[str, Any]] = []
    for customer, group in feature_rows.groupby(CUSTOMER, sort=False):
        group = group.reset_index(drop=True)
        detected_positions = np.flatnonzero(group["is_detected"].to_numpy())
        if not len(detected_positions):
            continue
        detected_times = pd.to_datetime(
            group.loc[detected_positions, TIMESTAMP]
        ).to_numpy()
        split_points = np.flatnonzero(
            np.diff(detected_times)
            > np.timedelta64(merge_gap_hours + 1, "h")
        ) + 1
        for burst in np.split(detected_positions, split_points):
            first_position = int(burst[0])
            last_position = int(burst[-1])
            start_position = max(0, first_position - 12)
            stop_position = min(len(group), first_position + 13)
            window = group.iloc[start_position:stop_position]
            pre_event = group.iloc[max(0, first_position - 24) : first_position][
                ENERGY
            ].to_numpy(dtype=np.float64)
            if not len(pre_event):
                pre_event = window[ENERGY].iloc[:1].to_numpy(dtype=np.float64)
            event_features = _event_features(
                window[ENERGY].to_numpy(dtype=np.float64),
                pre_event,
                pd.Timestamp(group.loc[first_position, TIMESTAMP]),
                event_offset=first_position - start_position,
            )
            detected_start = pd.Timestamp(group.loc[first_position, TIMESTAMP])
            detected_end = pd.Timestamp(group.loc[last_position, TIMESTAMP]) + pd.Timedelta(
                hours=1
            )
            event_rows.append(
                {
                    "event_id": f"EVT_{len(event_rows) + 1:06d}",
                    CUSTOMER: int(customer),
                    "start_time": detected_start,
                    "end_time": detected_end,
                    "duration_hours": float(
                        (detected_end - detected_start).total_seconds() / 3600
                    ),
                    "detected_points": int(len(burst)),
                    "max_anomaly_score": float(group.loc[burst, "anomaly_score"].max()),
                    LATITUDE: float(group.loc[first_position, LATITUDE]),
                    LONGITUDE: float(group.loc[first_position, LONGITUDE]),
                    "anomaly_type": classify_anomaly_type(
                        event_features, bundle["rule_thresholds"]
                    ),
                    **event_features,
                }
            )
    return pd.DataFrame(event_rows)


def classify_event_window(
    window_values: list[float] | np.ndarray,
    pre_event_values: list[float] | np.ndarray,
    timestamp: pd.Timestamp,
    model_path: str | Path,
) -> dict[str, Any]:
    """Apply deterministic rules to characterize a completed 25-hour event window."""
    bundle = joblib.load(model_path)
    if "rule_thresholds" not in bundle:
        raise ValueError("Model bundle is missing the anomaly-type rule thresholds.")
    window = np.asarray(window_values, dtype=np.float64)
    pre_event = np.asarray(pre_event_values, dtype=np.float64)
    if window.shape != (25,):
        raise ValueError("Event windows must contain exactly 25 hourly readings.")
    if pre_event.ndim != 1 or len(pre_event) < 1:
        raise ValueError("At least one pre-event reading is required for a baseline.")
    features = _event_features(window, pre_event, pd.Timestamp(timestamp))
    predicted = classify_anomaly_type(features, bundle["rule_thresholds"])
    return {
        "anomaly_type": predicted,
        "classification_method": "deterministic signal rules",
        "signal_features": features,
    }


class GridVisionExperiment:
    """Run the notebook stages while keeping train/validation/test data separated."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.profile: dict[str, Any] = {}
        self.customer_splits: dict[str, list[int]] = {}
        self.split_integrity: dict[str, Any] = {}
        self.boundaries: dict[str, pd.Timestamp] = {}
        self.detector: RandomForestClassifier | None = None
        self.threshold: float | None = None
        self.rule_thresholds: dict[str, float] = {}
        self.train_metadata: dict[str, Any] = {}
        self.metrics: dict[str, Any] = {}

    def audit_and_load(self) -> dict[str, Any]:
        self.profile = inspect_parquet(self.config.parquet_path)
        self.customer_splits, self.split_integrity = split_customers(
            self.config.parquet_path, self.config
        )
        sampled = load_customer_sample(self.config.parquet_path, self.customer_splits)
        if self.config.gold_features_path:
            gold_path = Path(self.config.gold_features_path)
            if not gold_path.is_file():
                raise FileNotFoundError(
                    f"Gold feature parquet does not exist: {gold_path}"
                )
            gold = pq.ParquetFile(gold_path)
            required_gold_columns = INPUT_COLUMNS + ["baseline"] + POINT_FEATURES
            missing_gold_columns = set(required_gold_columns) - set(gold.schema.names)
            if missing_gold_columns:
                raise ValueError(
                    "Gold feature parquet is missing required columns: "
                    f"{sorted(missing_gold_columns)}"
                )
            if gold.metadata.num_rows != len(sampled):
                raise ValueError(
                    "Gold feature row count does not match the sampled silver data: "
                    f"{gold.metadata.num_rows} != {len(sampled)}."
                )
        self.boundaries = temporal_boundaries(sampled)
        self.data = sampled
        self.train_history = sampled.loc[
            sampled[CUSTOMER].isin(self.customer_splits["train"])
            & (sampled[TIMESTAMP] < self.boundaries["train_end"])
        ].copy()
        self.validation_history = sampled.loc[
            sampled[CUSTOMER].isin(self.customer_splits["validation"])
            & (sampled[TIMESTAMP] < self.boundaries["validation_end"])
        ].copy()
        self.test_history = sampled.loc[
            sampled[CUSTOMER].isin(self.customer_splits["test"])
        ].copy()
        return {
            "profile": self.profile,
            "split_integrity": self.split_integrity,
            "sampled_rows": int(len(sampled)),
            "gold_features_path": self.config.gold_features_path,
            "temporal_boundaries": {
                key: value.isoformat() for key, value in self.boundaries.items()
            },
            "history_rows": {
                "train": int(len(self.train_history)),
                "validation": int(len(self.validation_history)),
                "test": int(len(self.test_history)),
            },
        }

    def _normal_features(self, history: pd.DataFrame) -> pd.DataFrame:
        """Read precomputed gold features when configured, otherwise engineer them."""
        if not self.config.gold_features_path:
            return add_causal_features(history)

        columns = INPUT_COLUMNS + ["baseline"] + POINT_FEATURES
        customer_ids = history[CUSTOMER].drop_duplicates().astype(int).tolist()
        gold = pq.read_table(
            self.config.gold_features_path,
            columns=columns,
            filters=[
                (CUSTOMER, "in", customer_ids),
                (TIMESTAMP, ">=", history[TIMESTAMP].min().to_pydatetime()),
                (TIMESTAMP, "<=", history[TIMESTAMP].max().to_pydatetime()),
            ],
        ).to_pandas()
        keys = [CUSTOMER, TIMESTAMP]
        if gold.duplicated(keys).any():
            raise ValueError("Gold feature parquet contains duplicate customer-hours.")
        expected = history[INPUT_COLUMNS].reset_index(drop=True)
        features = (
            expected[keys]
            .merge(gold, on=keys, how="left", sort=False, validate="one_to_one")
            .loc[:, columns]
        )
        if len(features) != len(expected) or features[POINT_FEATURES].isna().all(axis=1).any():
            raise ValueError(
                "Gold feature parquet does not cover every requested normal row."
            )
        actual = features[INPUT_COLUMNS].reset_index(drop=True)
        if not actual.equals(expected):
            raise ValueError(
                "Gold feature raw inputs do not match the current silver dataset."
            )
        return features

    def fit_binary_detector(self) -> dict[str, Any]:
        normal_train_features = self._normal_features(self.train_history)
        normal_train_features = normal_train_features.loc[
            normal_train_features[TIMESTAMP] < self.boundaries["train_end"]
        ]
        self.rule_thresholds = learn_rule_thresholds(
            normal_train_features, self.config
        )
        del normal_train_features
        training_data, self.train_events, self.train_event_counts = (
            generate_synthetic_events(
                self.train_history,
                self.boundaries["start"],
                self.boundaries["train_end"],
                self.config.training_events_per_class,
                self.config.random_seed + 1,
            )
        )
        training_features = add_causal_features(training_data)
        training_mask = training_features[TIMESTAMP] < self.boundaries["train_end"]
        training_labels = training_data.loc[
            training_mask, "injected_anomaly"
        ].to_numpy(dtype=np.uint8)
        self.detector, self.threshold, self.train_metadata = fit_detector(
            training_features.loc[training_mask].reset_index(drop=True),
            training_labels,
            self.config,
        )
        self.train_metadata["rule_thresholds"] = self.rule_thresholds
        del training_data, training_features

        validation_normal_features = self._normal_features(self.validation_history)
        validation_normal_mask = (
            (validation_normal_features[TIMESTAMP] >= self.boundaries["train_end"])
            & (validation_normal_features[TIMESTAMP] < self.boundaries["validation_end"])
        )
        self.validation_normal_scores = self.detector.predict_proba(
            validation_normal_features.loc[
                validation_normal_mask, POINT_FEATURES
            ].to_numpy(dtype=np.float32)
        )[:, 1]
        del validation_normal_features
        return {
            **self.train_metadata,
            "validation_normal_rows": int(len(self.validation_normal_scores)),
            "signal_detector_features": {
                "time_domain": 15,
                "fft": 7,
                "haar_wavelet": 8,
            },
            "type_classifier": "deterministic thresholds/rules; no type prediction model",
        }

    def calibrate_detector_and_rules(self) -> dict[str, Any]:
        if self.detector is None or self.threshold is None:
            raise RuntimeError("Fit the anomaly detector before calibration.")
        validation_data, validation_events, validation_event_counts = (
            generate_synthetic_events(
                self.validation_history,
                self.boundaries["train_end"],
                self.boundaries["validation_end"],
                self.config.evaluation_events_per_class,
                self.config.random_seed + 2,
            )
        )
        validation_features = add_causal_features(validation_data)
        validation_mask = (
            (validation_features[TIMESTAMP] >= self.boundaries["train_end"])
            & (validation_features[TIMESTAMP] < self.boundaries["validation_end"])
        )
        validation_labels = validation_data.loc[
            validation_mask, "injected_anomaly"
        ].to_numpy(dtype=np.uint8)
        validation_scores = self.detector.predict_proba(
            validation_features.loc[validation_mask, POINT_FEATURES].to_numpy(
                dtype=np.float32
            )
        )[:, 1]
        precision, recall, candidate_thresholds = precision_recall_curve(
            validation_labels, validation_scores
        )
        candidate_f1 = (
            2 * precision[:-1] * recall[:-1] / (precision[:-1] + recall[:-1] + 1e-12)
        )
        if not len(candidate_thresholds):
            raise RuntimeError("Validation data did not provide threshold candidates.")
        best_index = int(np.argmax(candidate_f1))
        self.metrics["training_quantile_threshold"] = float(self.threshold)
        self.threshold = float(candidate_thresholds[best_index])
        self.train_metadata["training_quantile_threshold"] = self.metrics[
            "training_quantile_threshold"
        ]
        self.train_metadata["selected_validation_threshold"] = self.threshold
        self.train_metadata["threshold_selection"] = (
            "maximum validation F1 on held-out synthetic events"
        )
        self.metrics["validation_normal_false_alert_rate"] = float(
            np.mean(self.validation_normal_scores >= self.threshold)
        )
        validation_metrics, _ = evaluate_detection(
            self.detector,
            self.threshold,
            validation_features.loc[validation_mask].reset_index(drop=True),
            validation_labels,
            self.rule_thresholds,
            validation_events,
        )
        self.metrics["validation_detection"] = validation_metrics
        self.metrics["validation_classification"] = evaluate_rule_classification(
            validation_events, self.rule_thresholds
        )
        self.metrics["synthetic_event_counts"] = {
            "train": self.train_event_counts,
            "validation": validation_event_counts,
        }
        return {
            "training_events": self.train_event_counts,
            "validation_events": validation_event_counts,
            "validation_detection": validation_metrics,
            "selected_threshold": self.threshold,
            "validation_normal_false_alert_rate": self.metrics[
                "validation_normal_false_alert_rate"
            ],
            "validation_classification": self.metrics["validation_classification"],
        }

    def evaluate_held_out_test(self) -> dict[str, Any]:
        if self.detector is None or self.threshold is None:
            raise RuntimeError("Fit and calibrate the detector before test evaluation.")
        test_data, test_events, test_event_counts = generate_synthetic_events(
            self.test_history,
            self.boundaries["validation_end"],
            self.boundaries["stop"],
            self.config.evaluation_events_per_class,
            self.config.random_seed + 3,
        )
        self.test_injected_data = test_data
        self.test_ground_truth_events = test_events.copy()
        test_features = add_causal_features(test_data)
        test_mask = test_features[TIMESTAMP] >= self.boundaries["validation_end"]
        test_labels = test_data.loc[test_mask, "injected_anomaly"].to_numpy(
            dtype=np.uint8
        )
        detection_metrics, self.scored_test_points = evaluate_detection(
            self.detector,
            self.threshold,
            test_features.loc[test_mask].reset_index(drop=True),
            test_labels,
            self.rule_thresholds,
            test_events,
        )
        classification_metrics = evaluate_rule_classification(
            test_events, self.rule_thresholds
        )
        self.metrics["test_detection"] = detection_metrics
        self.metrics["test_classification"] = classification_metrics
        self.metrics["synthetic_event_counts"]["test"] = test_event_counts
        self.metrics["test_customer_count"] = int(
            test_data.loc[test_mask, CUSTOMER].nunique()
        )
        return {
            "test_detection": detection_metrics,
            "test_classification": classification_metrics,
            "test_events": test_event_counts,
        }

    def localize(self) -> pd.DataFrame:
        if not hasattr(self, "scored_test_points") or not hasattr(
            self, "test_ground_truth_events"
        ):
            raise RuntimeError("Evaluate the held-out test before localization.")
        if self.detector is None or self.threshold is None:
            raise RuntimeError("Fit and calibrate the detector before localization.")
        localization_config = EventLocalizationConfig(
            h3_resolution=self.config.h3_resolution,
            spatial_radius_km=self.config.spatial_radius_km,
            dbscan_min_customers=self.config.spatial_dbscan_min_customers,
            maximum_start_time_difference=pd.Timedelta(
                minutes=self.config.maximum_start_time_difference_minutes
            ),
            minimum_temporal_overlap=self.config.minimum_temporal_overlap,
            maximum_interval_gap=pd.Timedelta(
                minutes=self.config.maximum_interval_gap_minutes
            ),
        )
        prediction_bundle = {
            "detector": self.detector,
            "detector_threshold": self.threshold,
            "rule_thresholds": self.rule_thresholds,
            "point_features": POINT_FEATURES,
        }
        self.predicted_anomaly_windows = _predict_anomaly_events_from_bundle(
            self.test_injected_data[INPUT_COLUMNS], prediction_bundle
        )
        anomaly_records = prepare_anomaly_records(self.predicted_anomaly_windows)
        self.localized_records, _ = form_events(anomaly_records, localization_config)
        self.localized = generate_event_summary(
            self.localized_records,
            population_customer_count=len(self.customer_splits["test"]),
            config=localization_config,
        )
        self.event_localization_metrics = evaluate_events(
            self.localized,
            self.test_ground_truth_events,
            localization_config,
        )
        anomalous_customers = set(self.localized_records["customer_id"].unique())
        normal_customers = (
            self.test_history[[CUSTOMER, LATITUDE, LONGITUDE]]
            .drop_duplicates(CUSTOMER)
            .loc[lambda frame: ~frame[CUSTOMER].isin(anomalous_customers)]
        )
        self.event_visualizations = visualize_events(
            self.localized_records,
            self.localized,
            Path(self.config.report_dir) / "event_visualizations",
            normal_customers=normal_customers,
        )
        return self.localized

    def save_artifacts(self) -> dict[str, str]:
        if self.detector is None or self.threshold is None or not self.rule_thresholds:
            raise RuntimeError("Complete training before saving model artifacts.")
        if not hasattr(self, "localized_records") or not hasattr(
            self, "event_localization_metrics"
        ):
            raise RuntimeError("Run event localization before saving report artifacts.")
        model_path = save_model_bundle(
            self.config.model_path,
            self.detector,
            self.threshold,
            self.rule_thresholds,
            self.config,
            self.train_metadata,
            self.metrics,
        )
        report_directory = Path(self.config.report_dir)
        report_directory.mkdir(parents=True, exist_ok=True)
        metrics_path = report_directory / "evaluation_metrics.json"
        import json

        report = {
            "source_profile": self.profile,
            "split_integrity": self.split_integrity,
            "temporal_boundaries": {
                key: value.isoformat() for key, value in self.boundaries.items()
            },
            "training_metadata": self.train_metadata,
            "metrics": {
                **self.metrics,
                "spatial_event_localization": self.event_localization_metrics,
            },
            "spatial_temporal_config": {
                "h3_resolution": self.config.h3_resolution,
                "spatial_radius_km": self.config.spatial_radius_km,
                "spatial_dbscan_min_customers": self.config.spatial_dbscan_min_customers,
                "maximum_start_time_difference_minutes": self.config.maximum_start_time_difference_minutes,
                "minimum_temporal_overlap": self.config.minimum_temporal_overlap,
                "maximum_interval_gap_minutes": self.config.maximum_interval_gap_minutes,
                "temporal_components_are_transitive": True,
            },
            "limitations": [
                "The source contains normal-only measurements; reported anomaly results "
                "use separately injected synthetic events.",
                "The model was fit and evaluated on sampled complete customer groups; "
                "results are not a full-population deployment benchmark.",
                "DBSCAN output is geographic correlation, not confirmed feeder or "
                "transformer localization.",
                "Synthetic ground truth contains independent customer events rather "
                "than labeled common incidents, so it cannot validate local-area or "
                "multi-area scope accuracy.",
            ],
        }
        with metrics_path.open("w", encoding="utf-8") as file:
            json.dump(report, file, indent=2, default=str)
        localization_path = report_directory / "test_geographic_clusters.csv"
        self.localized.to_csv(localization_path, index=False)
        detected_events = self.predicted_anomaly_windows
        event_path = report_directory / "test_detected_events.csv"
        detected_events.to_csv(event_path, index=False)
        anomaly_records_path = report_directory / "spatial_event_anomaly_records.csv"
        self.localized_records.to_csv(anomaly_records_path, index=False)
        event_summary_path = report_directory / "spatial_temporal_events.csv"
        self.localized.to_csv(event_summary_path, index=False)
        event_evaluation_path = report_directory / "event_localization_evaluation.json"
        with event_evaluation_path.open("w", encoding="utf-8") as file:
            json.dump(self.event_localization_metrics, file, indent=2, default=str)
        return {
            "model": str(model_path),
            "metrics": str(metrics_path),
            "localization": str(localization_path),
            "detected_events": str(event_path),
            "spatial_event_records": str(anomaly_records_path),
            "spatial_temporal_events": str(event_summary_path),
            "event_localization_evaluation": str(event_evaluation_path),
            "event_visualizations": self.event_visualizations,
        }

    def run(self) -> dict[str, Any]:
        self.audit_and_load()
        self.fit_binary_detector()
        self.calibrate_detector_and_rules()
        self.evaluate_held_out_test()
        localized = self.localize()
        artifacts = self.save_artifacts()
        return {
            "metrics": self.metrics,
            "localized_event_count": int(len(localized)),
            "artifacts": artifacts,
        }
