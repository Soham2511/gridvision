"""Fit category-aware building clusters and persist assignments and profiles."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .config import SegmentationSettings
from .data_pipeline import IDENTIFIER_COLUMNS, _atomic_json
from .evaluation import evaluate_candidates
from .preprocessing import BehaviourFeatureEngineer, build_preprocessor

logger = logging.getLogger("gridvision.segmentation.model")

PROFILE_METADATA = sorted(IDENTIFIER_COLUMNS) + ["coverage_ratio", "observed_hours"]
NON_FEATURE_COLUMNS = set(PROFILE_METADATA)
BEHAVIOUR_FEATURE_COLUMNS = [
    "mean_energy_kwh",
    "median_energy_kwh",
    "stddev_energy_kwh",
    "p95_energy_kwh",
    "peak_energy_kwh",
    "night_energy_share",
    "morning_energy_share",
    "afternoon_energy_share",
    "evening_energy_share",
    "weekday_mean_hourly_energy_kwh",
    "weekend_mean_hourly_energy_kwh",
    "coefficient_of_variation",
    "peak_to_average_ratio",
    "weekend_to_weekday_ratio",
    "peak_hour_sin",
    "peak_hour_cos",
    "mean_daily_stddev_kwh",
    "daily_energy_stddev_kwh",
    "mean_daily_energy_kwh",
    "monthly_energy_cv",
    "monthly_peak_to_average",
]


def _slug(value: Any) -> str:
    text = re.sub(r"[^A-Z0-9]+", "_", str(value).upper()).strip("_")
    return text or "UNKNOWN"


def _profile_label(
    cluster_rows: pd.DataFrame,
    group_rows: pd.DataFrame,
    feature_columns: list[str],
) -> str:
    friendly_names = {
        "log_mean_energy_kwh": "consumption intensity",
        "coefficient_of_variation": "consumption variability",
        "night_energy_share": "night-time consumption share",
        "morning_energy_share": "morning consumption share",
        "afternoon_energy_share": "afternoon consumption share",
        "weekend_to_weekday_ratio": "weekend-to-weekday use",
        "p95_to_average_ratio": "high-consumption peakiness",
        "daily_energy_cv": "daily consumption variability",
        "monthly_energy_cv": "month-to-month variability",
        "monthly_peak_to_average": "monthly peakiness",
    }
    candidates = []
    for feature in feature_columns:
        global_values = pd.to_numeric(group_rows[feature], errors="coerce").dropna()
        cluster_values = pd.to_numeric(cluster_rows[feature], errors="coerce").dropna()
        if global_values.empty or cluster_values.empty:
            continue
        median = float(global_values.median())
        spread = float(global_values.quantile(0.75) - global_values.quantile(0.25))
        if spread <= 0 or not np.isfinite(spread):
            continue
        delta = (float(cluster_values.median()) - median) / spread
        if abs(delta) >= 0.2:
            candidates.append((abs(delta), feature, "higher" if delta > 0 else "lower"))
    candidates.sort(reverse=True)
    descriptors = [
        f"{direction} {friendly_names.get(feature, feature.replace('_', ' '))}"
        for _, feature, direction in candidates[:2]
    ]
    peak_features = {"peak_hour_sin", "peak_hour_cos"}
    if any(feature in peak_features for _, feature, _ in candidates[:2]):
        peak_hours = pd.to_numeric(cluster_rows.get("peak_consumption_hour"), errors="coerce").dropna()
        if not peak_hours.empty:
            peak_hour = int(round(float(peak_hours.median()))) % 24
            descriptors = [
                descriptor for descriptor in descriptors
                if "peak hour" not in descriptor
            ]
            descriptors.insert(0, f"peak around {peak_hour:02d}:00")
    if not descriptors:
        return "Typical profile"
    descriptors = [descriptor[0].upper() + descriptor[1:] for descriptor in descriptors]
    return " · ".join(descriptors)


def _safe_model_bundle(
    *,
    preprocessor: Any,
    model: Any,
    feature_columns: list[str],
    algorithm: str,
    cluster_ids: list[str],
    category: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "preprocessor": preprocessor,
        "model": model,
        "feature_columns": feature_columns,
        "algorithm": algorithm,
        "cluster_ids": cluster_ids,
        "general_use_type": category,
        "metadata": metadata,
    }


def fit_and_publish(
    features_path: Path,
    settings: SegmentationSettings,
) -> dict[str, Any]:
    """Train model(s), create interpretable profiles and publish parquet outputs."""
    features_path = features_path.expanduser().resolve()
    if not features_path.is_file():
        raise FileNotFoundError(f"Building feature table not found: {features_path}")
    feature_rows = pd.read_parquet(features_path)
    if feature_rows.empty:
        raise ValueError("Building feature table is empty")
    if "OBJECTID" not in feature_rows or feature_rows["OBJECTID"].isna().any():
        raise ValueError("Feature table must contain non-null OBJECTID values")
    if feature_rows["OBJECTID"].duplicated().any():
        raise ValueError("Expected one feature row per OBJECTID")

    missing_feature_columns = sorted(set(BEHAVIOUR_FEATURE_COLUMNS) - set(feature_rows.columns))
    if missing_feature_columns:
        raise ValueError(f"Feature table is missing behaviour features: {missing_feature_columns}")
    feature_columns = [
        column
        for column in BEHAVIOUR_FEATURE_COLUMNS
        if feature_rows[column].notna().any()
    ]
    if not feature_columns:
        raise ValueError("No numeric behavioural features are available")
    feature_rows[feature_columns] = feature_rows[feature_columns].replace(
        [np.inf, -np.inf], np.nan
    )

    category_values = feature_rows["GeneralUseType"].fillna("UNKNOWN").astype(str)
    category_sizes = category_values.value_counts(dropna=False)
    eligible_categories = sorted(
        category
        for category, size in category_sizes.items()
        if size >= settings.minimum_category_size
    )
    pooled_categories = sorted(
        category for category in category_sizes.index if category not in eligible_categories
    )
    if eligible_categories:
        groups = [(category, category_values == category) for category in eligible_categories]
        if pooled_categories:
            groups.append(
                (
                    "SHARED_SMALL_CATEGORIES",
                    category_values.isin(pooled_categories),
                )
            )
    else:
        groups = [("ALL", pd.Series(True, index=feature_rows.index))]

    output_dir = settings.output_dir
    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    assignment_frames: list[pd.DataFrame] = []
    profile_rows: list[dict[str, Any]] = []
    evaluation_by_model: dict[str, Any] = {}
    model_metadata: list[dict[str, Any]] = []
    skipped_categories: list[dict[str, Any]] = []
    feature_diagnostics: dict[str, Any] = {}

    for category, mask in groups:
        group = feature_rows.loc[mask].copy()
        if len(group) < max(4, settings.min_k + 1):
            skipped_categories.append(
                {"GeneralUseType": category, "building_count": len(group), "reason": "too few buildings for clustering"}
            )
            continue
        x_raw = group[feature_columns].astype(float)
        absolute_correlation = x_raw.corr().abs()
        high_correlation_pairs = [
            {
                "feature_a": left,
                "feature_b": right,
                "absolute_correlation": float(absolute_correlation.loc[left, right]),
            }
            for index, left in enumerate(feature_columns)
            for right in feature_columns[index + 1 :]
            if pd.notna(absolute_correlation.loc[left, right])
            and absolute_correlation.loc[left, right] >= 0.9
        ]
        preprocessor = build_preprocessor(settings.correlation_threshold)
        try:
            x = preprocessor.fit_transform(x_raw)
        except ValueError as exc:
            logger.warning("Skipping %s due to preprocessing failure: %s", category, exc)
            skipped_categories.append(
                {"GeneralUseType": category, "building_count": len(group), "reason": str(exc)}
            )
            continue
        if x.shape[1] == 0:
            logger.warning("Skipping %s: no varying features remain", category)
            skipped_categories.append(
                {"GeneralUseType": category, "building_count": len(group), "reason": "no varying features remain"}
            )
            continue
        engineered_names = list(
            preprocessor.named_steps["behaviour_features"].get_feature_names_out()
        )
        correlation_names = list(
            preprocessor.named_steps["remove_correlated"].get_feature_names_out()
        )
        retained_mask = preprocessor.named_steps["remove_constant"].get_support()
        retained_features = [
            feature for feature, retained in zip(correlation_names, retained_mask) if retained
        ]
        imputation_medians = preprocessor.named_steps["imputer"].statistics_
        scaling_center = preprocessor.named_steps["scaler"].center_
        scaling_scale = preprocessor.named_steps["scaler"].scale_
        selected, evaluation = evaluate_candidates(
            np.asarray(x),
            min_k=settings.min_k,
            max_k=settings.max_k,
            seed=settings.random_seed,
            include_hdbscan=True,
            minimum_cluster_size=settings.minimum_cluster_size,
            minimum_cluster_fraction=settings.minimum_cluster_fraction,
        )
        evaluation_by_model[_slug(category)] = evaluation
        engineered_values = preprocessor.named_steps["behaviour_features"].transform(x_raw)
        engineered_correlation = engineered_values.corr().abs()
        post_reduction_pairs = [
            {
                "feature_a": left,
                "feature_b": right,
                "absolute_correlation": float(engineered_correlation.loc[left, right]),
            }
            for index, left in enumerate(engineered_names)
            for right in engineered_names[index + 1 :]
            if pd.notna(engineered_correlation.loc[left, right])
            and engineered_correlation.loc[left, right] >= 0.9
        ]
        correlated_values = preprocessor.named_steps["remove_correlated"].transform(
            engineered_values
        )
        retained_correlation = correlated_values.corr().abs()
        remaining_correlation_pairs = [
            {
                "feature_a": left,
                "feature_b": right,
                "absolute_correlation": float(retained_correlation.loc[left, right]),
            }
            for index, left in enumerate(correlation_names)
            for right in correlation_names[index + 1 :]
            if pd.notna(retained_correlation.loc[left, right])
            and retained_correlation.loc[left, right] >= 0.9
        ]
        feature_diagnostics[_slug(category)] = {
            "building_count": len(group),
            "high_correlation_raw_pairs": high_correlation_pairs,
            "high_correlation_after_behaviour_transforms": post_reduction_pairs,
            "high_correlation_after_filter": remaining_correlation_pairs,
            "raw_feature_count": len(feature_columns),
            "engineered_feature_count": len(engineered_names),
            "correlation_filtered_feature_count": len(correlation_names),
            "retained_feature_count": len(retained_features),
            "retained_features": retained_features,
            "correlation_filtered_features": [
                feature for feature in engineered_names if feature not in correlation_names
            ],
            "constant_features_removed": [
                feature for feature, retained in zip(correlation_names, retained_mask) if not retained
            ],
        }
        if selected is None:
            skipped_categories.append(
                {
                    "GeneralUseType": category,
                    "building_count": len(group),
                    "reason": "no assignable candidate passed the minimum cluster size gate",
                }
            )
            continue
        raw_labels = np.asarray(selected["labels"])
        algorithm = str(selected["algorithm"])
        category_slug = _slug(category)
        cluster_values = sorted(int(value) for value in np.unique(raw_labels) if value >= 0)
        cluster_names = {value: f"{category_slug}_{value}" for value in cluster_values}
        output_labels = [cluster_names.get(int(value)) for value in raw_labels]
        group_assignments = group[PROFILE_METADATA].copy()
        group_assignments["segment_id"] = output_labels
        if algorithm == "gmm" and hasattr(selected["model"], "predict_proba"):
            group_assignments["cluster_probability"] = selected["model"].predict_proba(x).max(axis=1)
        elif algorithm == "hdbscan" and hasattr(selected["model"], "probabilities_"):
            group_assignments["cluster_probability"] = selected["model"].probabilities_
        else:
            group_assignments["cluster_probability"] = np.nan
        group_assignments["model_category"] = category
        assignment_frames.append(group_assignments)

        model_path = models_dir / f"{category_slug.lower()}_model.joblib"
        bundle = _safe_model_bundle(
            preprocessor=preprocessor,
            model=selected["model"],
            feature_columns=feature_columns,
            algorithm=algorithm,
            cluster_ids=list(cluster_names.values()),
            category=category,
            metadata={
                "random_seed": settings.random_seed,
                "imputation_strategy": "median",
                "scaler": "RobustScaler",
                "correlation_threshold": settings.correlation_threshold,
                "input_features": feature_columns,
                "behaviour_features": engineered_names,
                "correlation_filtered_features": [
                    feature for feature in engineered_names if feature not in correlation_names
                ],
                "retained_features": retained_features,
                "constant_features_removed": [
                    feature for feature, retained in zip(correlation_names, retained_mask) if not retained
                ],
                "imputation_medians": {
                    feature: float(value)
                    for feature, value in zip(correlation_names, imputation_medians)
                },
                "scaler_center": {
                    feature: float(value)
                    for feature, value in zip(retained_features, scaling_center)
                },
                "scaler_scale": {
                    feature: float(value)
                    for feature, value in zip(retained_features, scaling_scale)
                },
            },
        )
        model_stage = model_path.with_suffix(".joblib.stage")
        joblib.dump(bundle, model_stage)
        model_stage.replace(model_path)

        local_rows = group.copy()
        for feature in correlation_names:
            local_rows[feature] = correlated_values[feature]
        local_rows["segment_id"] = output_labels
        local_rows["model_category"] = category
        for raw_cluster, segment_id in cluster_names.items():
            cluster_mask = np.asarray(raw_labels) == raw_cluster
            cluster = local_rows.loc[cluster_mask]
            profile = {
                "segment_id": segment_id,
                "segment_name": _profile_label(cluster, local_rows, retained_features),
                "model_category": category,
                "building_count": int(len(cluster)),
                "share_of_model_buildings": float(len(cluster) / len(local_rows)),
                "algorithm": algorithm,
                "feature_medians": {
                    feature: float(cluster[feature].median())
                    for feature in feature_columns
                    if cluster[feature].notna().any()
                },
                "behaviour_feature_medians": {
                    feature: float(cluster[feature].median())
                    for feature in retained_features
                    if cluster[feature].notna().any()
                },
                "dominant_general_use_type": (
                    str(cluster["GeneralUseType"].mode().iloc[0])
                    if "GeneralUseType" in cluster and not cluster["GeneralUseType"].mode().empty
                    else None
                ),
            }
            profile_rows.append(profile)
        model_record = {
            "model_category": category,
            "algorithm": algorithm,
            "model_path": str(model_path),
            "feature_columns": feature_columns,
            "transformed_feature_columns": retained_features,
            "cluster_ids": list(cluster_names.values()),
            "building_count": len(group),
            "evaluation": evaluation["selected"],
        }
        model_metadata.append(model_record)

    _atomic_json(output_dir / "feature_diagnostics.json", feature_diagnostics)
    if assignment_frames:
        current_assignments = pd.concat(assignment_frames, ignore_index=True)
        current_assignments = current_assignments.loc[
            current_assignments["segment_id"].notna()
        ]
        assignment_frames = [current_assignments]
        assigned_ids = set(current_assignments["OBJECTID"])
    else:
        assigned_ids = set()
    unresolved = feature_rows.loc[~feature_rows["OBJECTID"].isin(assigned_ids)]
    if not unresolved.empty:
        unresolved_categories = unresolved["GeneralUseType"].fillna("UNKNOWN").astype(str)
        for category, mask in unresolved.groupby(unresolved_categories, dropna=False).groups.items():
            category_rows = unresolved.loc[mask]
            segment_id = f"{_slug(category)}_UNCLUSTERED"
            fallback = category_rows[PROFILE_METADATA].copy()
            fallback["segment_id"] = segment_id
            fallback["cluster_probability"] = np.nan
            fallback["model_category"] = "UNCLUSTERED"
            assignment_frames.append(fallback)
            profile_rows.append(
                {
                    "segment_id": segment_id,
                    "segment_name": "Unclustered: insufficient data or no valid model",
                    "model_category": "UNCLUSTERED",
                    "building_count": int(len(category_rows)),
                    "share_of_model_buildings": 1.0,
                    "algorithm": "unclustered",
                    "feature_medians": {
                        feature: float(category_rows[feature].median())
                        for feature in feature_columns
                        if category_rows[feature].notna().any()
                    },
                    "behaviour_feature_medians": {},
                    "dominant_general_use_type": (
                        None if category == "UNKNOWN" else str(category)
                    ),
                }
            )
            skipped_categories.append(
                {
                    "GeneralUseType": None if category == "UNKNOWN" else str(category),
                    "building_count": int(len(category_rows)),
                    "reason": "retained in an unclustered assignment because no valid model was available",
                }
            )
    if not assignment_frames:
        _atomic_json(output_dir / "model_selection_report.json", evaluation_by_model)
        raise ValueError("No feature rows were available for segmentation assignments")
    assignments = pd.concat(assignment_frames, ignore_index=True)
    assignments_path = output_dir / "consumer_assignments.parquet"
    _write_parquet(assignments, assignments_path)
    profiles = pd.DataFrame(profile_rows)
    _write_parquet(profiles, output_dir / "cluster_profiles.parquet")
    distribution = (
        assignments.dropna(subset=["segment_id"])
        .groupby(
            ["GeneralUseType", "segment_id", "model_category"], dropna=False
        )
        .agg(building_count=("OBJECTID", "nunique"))
        .reset_index()
    )
    distribution["share_of_assigned_buildings"] = distribution["building_count"] / max(
        1, assignments["OBJECTID"].nunique()
    )
    _write_parquet(distribution, output_dir / "segment_distribution.parquet")
    feature_report_path = output_dir / "reports" / "feature_generation.json"
    feature_report = (
        json.loads(feature_report_path.read_text(encoding="utf-8"))
        if feature_report_path.is_file()
        else {}
    )
    output_metadata = {
        "model_version": "segmentation-v1-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "observation_start": feature_report.get("observation_start"),
        "observation_end_exclusive": feature_report.get("observation_end_exclusive"),
        "source_feature_table": str(features_path),
        "source_feature_columns": feature_columns,
        "features": {
            model["model_category"]: feature_diagnostics.get(
                _slug(model["model_category"]), {}
            ).get("retained_features", [])
            for model in model_metadata
        },
        "metadata_excluded_from_clustering": sorted(NON_FEATURE_COLUMNS),
        "minimum_category_size": settings.minimum_category_size,
        "minimum_cluster_size": settings.minimum_cluster_size,
        "minimum_cluster_fraction": settings.minimum_cluster_fraction,
        "correlation_threshold": settings.correlation_threshold,
        "category_building_counts": {
            str(category): int(size) for category, size in category_sizes.items()
        },
        "pooled_small_categories": [str(category) for category in pooled_categories],
        "trained_models": model_metadata,
        "skipped_categories": skipped_categories,
        "evaluation_method": "multi-criteria metrics plus cluster-size validity gate",
        "assignment_count": int(len(assignments)),
        "unassigned_feature_buildings": int(len(feature_rows) - assignments["OBJECTID"].nunique()),
    }
    _atomic_json(output_dir / "model_metadata.json", output_metadata)
    _atomic_json(output_dir / "model_selection_report.json", evaluation_by_model)
    return output_metadata


def _write_parquet(frame: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stage_path = output_path.with_suffix(output_path.suffix + ".stage")
    frame.to_parquet(stage_path, index=False)
    stage_path.replace(output_path)

