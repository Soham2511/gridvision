"""Regional segment summaries, temporal profiles, and explainable survey ranking."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import SegmentationSettings
from .data_pipeline import _atomic_json, _connect, _parquet_sql
from .clustering import _write_parquet

logger = logging.getLogger("gridvision.segmentation.geospatial")

DEFAULT_PRIORITY_WEIGHTS = {
    "target_segment_concentration": 0.4,
    "peak_intensity": 0.3,
    "consumption_variability": 0.3,
}


def _priority_weights() -> dict[str, float]:
    raw = os.getenv("SEGMENTATION_PRIORITY_WEIGHTS", "").strip()
    if not raw:
        weights = DEFAULT_PRIORITY_WEIGHTS.copy()
    else:
        try:
            incoming = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("SEGMENTATION_PRIORITY_WEIGHTS must be a JSON object") from exc
        unknown = set(incoming) - set(DEFAULT_PRIORITY_WEIGHTS)
        if unknown:
            raise ValueError(f"Unknown survey-priority factors: {sorted(unknown)}")
        weights = {key: float(incoming.get(key, value)) for key, value in DEFAULT_PRIORITY_WEIGHTS.items()}
    if any(value < 0 or not np.isfinite(value) for value in weights.values()):
        raise ValueError("Survey-priority weights must be finite non-negative values")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("At least one survey-priority weight must be positive")
    return {key: value / total for key, value in weights.items()}


def _minmax_100(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    minimum, maximum = numeric.min(), numeric.max()
    if pd.isna(minimum) or pd.isna(maximum):
        return pd.Series(0.0, index=values.index)
    if maximum == minimum:
        return pd.Series(50.0, index=values.index)
    return ((numeric - minimum) / (maximum - minimum) * 100).fillna(0.0)


def publish_geospatial_outputs(
    settings: SegmentationSettings,
    assignments_path: Path | None = None,
    feature_path: Path | None = None,
) -> dict[str, Any]:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    assignments_path = assignments_path or settings.output_dir / "consumer_assignments.parquet"
    feature_path = feature_path or settings.feature_path
    source = settings.source_path.expanduser().resolve()
    if not source.is_file() or not assignments_path.is_file() or not feature_path.is_file():
        raise FileNotFoundError("Source, building features, and assignments are required")
    assignments_sql = _parquet_sql(assignments_path)
    features_sql = _parquet_sql(feature_path)
    source_sql = _parquet_sql(source)
    con = _connect(settings)
    try:
        for region_column, label in (("id.grid.coarse", "coarse"), ("id.grid.finer", "finer")):
            query = f"""
            COPY (
              SELECT
                a."{region_column}" AS region_id,
                a.segment_id,
                a.model_category,
                a.GeneralUseType,
                COUNT(DISTINCT a.OBJECTID) AS building_count,
                AVG(f.mean_energy_kwh) AS mean_energy_kwh,
                AVG(f.p95_energy_kwh) AS mean_p95_energy_kwh,
                AVG(f.peak_to_average_ratio) AS mean_peak_to_average_ratio,
                AVG(f.coefficient_of_variation) AS mean_coefficient_of_variation,
                AVG(f.coverage_ratio) AS mean_coverage_ratio,
                AVG(a.cluster_probability) AS mean_cluster_probability,
                AVG(a.latitude) AS latitude,
                AVG(a.longitude) AS longitude
              FROM {assignments_sql} a
              LEFT JOIN {features_sql} f USING (OBJECTID)
              WHERE a."{region_column}" IS NOT NULL AND a.segment_id IS NOT NULL
              GROUP BY 1, 2, 3, 4
            ) TO '{(settings.output_dir / f'region_summary_{label}.parquet.stage').as_posix()}'
            (FORMAT PARQUET, COMPRESSION ZSTD)
            """
            con.execute(query)
            staged = settings.output_dir / f"region_summary_{label}.parquet.stage"
            staged.replace(settings.output_dir / f"region_summary_{label}.parquet")

        # Profiles are averages over actual recorded readings; no missing hour is filled with zero.
        start_window = settings.window_end
        if start_window is None:
            start_window = con.execute(
                f"SELECT CAST(MAX(timestamp) AS DATE) FROM {source_sql}"
            ).fetchone()[0]
        end_exclusive = con.execute("SELECT CAST(? AS DATE) + INTERVAL 1 DAY", [start_window]).fetchone()[0]
        start = con.execute(
            "SELECT CAST(? AS DATE) - (? * INTERVAL 1 MONTH)",
            [end_exclusive, settings.window_months],
        ).fetchone()[0]
        for kind, date_expr, output_name in (
            ("hourly", "EXTRACT(hour FROM CAST(s.timestamp AS TIMESTAMP))", "cluster_hourly_profile.parquet"),
            ("daily", "EXTRACT(dow FROM CAST(s.timestamp AS TIMESTAMP))", "cluster_daily_profile.parquet"),
            ("monthly", "EXTRACT(month FROM CAST(s.timestamp AS TIMESTAMP))", "cluster_monthly_profile.parquet"),
        ):
            intermediate = f"""
              SELECT a.segment_id, a.model_category, a.GeneralUseType, a.OBJECTID,
                     {date_expr} AS period_index,
                     AVG(TRY_CAST(s.normalized_building_energy_kwh AS DOUBLE)) AS building_period_mean
              FROM {source_sql} s
              JOIN {assignments_sql} a ON a.OBJECTID = s.OBJECTID
              WHERE CAST(s.timestamp AS TIMESTAMP) >= CAST(? AS TIMESTAMP)
                AND CAST(s.timestamp AS TIMESTAMP) < CAST(? AS TIMESTAMP)
                AND a.segment_id IS NOT NULL
                AND isfinite(TRY_CAST(s.normalized_building_energy_kwh AS DOUBLE))
                AND TRY_CAST(s.normalized_building_energy_kwh AS DOUBLE) >= 0
              GROUP BY a.segment_id, a.model_category, a.GeneralUseType, a.OBJECTID, period_index
            """
            staged = settings.output_dir / f"{output_name}.stage"
            query = f"""
              COPY (
                SELECT segment_id, model_category, GeneralUseType, period_index,
                       AVG(building_period_mean) AS mean_energy_kwh,
                       COUNT(DISTINCT OBJECTID) AS contributing_buildings
                FROM ({intermediate}) grouped
                GROUP BY segment_id, model_category, GeneralUseType, period_index
              ) TO '{staged.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """
            con.execute(query, [start, end_exclusive])
            staged.replace(settings.output_dir / output_name)

        coarse_path = settings.output_dir / "region_summary_coarse.parquet"
        coarse = pd.read_parquet(coarse_path)
        # Reduce segment rows to one survey record per coarse region.
        by_segment = coarse.copy()
        weights = _priority_weights()
        targets = {
            item.strip()
            for item in os.getenv("SEGMENTATION_PRIORITY_TARGETS", "").split(",")
            if item.strip()
        }
        by_segment["target_segment_buildings"] = by_segment.apply(
            lambda row: row["building_count"]
            if (row["segment_id"] in targets if targets else True)
            else 0,
            axis=1,
        )
        by_segment["_weighted_peak"] = by_segment["mean_peak_to_average_ratio"] * by_segment["building_count"]
        by_segment["_weighted_cv"] = by_segment["mean_coefficient_of_variation"] * by_segment["building_count"]
        by_segment["_weighted_p95"] = by_segment["mean_p95_energy_kwh"] * by_segment["building_count"]
        regional = by_segment.groupby(
            ["region_id", "GeneralUseType"], dropna=False
        ).agg(
            building_count=("building_count", "sum"),
            target_segment_buildings=("target_segment_buildings", "sum"),
            _weighted_peak=("_weighted_peak", "sum"),
            _weighted_cv=("_weighted_cv", "sum"),
            _weighted_p95=("_weighted_p95", "sum"),
            latitude=("latitude", "mean"),
            longitude=("longitude", "mean"),
        ).reset_index()
        denominator = regional["building_count"].replace(0, np.nan)
        regional["mean_peak_to_average_ratio"] = regional["_weighted_peak"] / denominator
        regional["mean_coefficient_of_variation"] = regional["_weighted_cv"] / denominator
        regional["mean_p95_energy_kwh"] = regional["_weighted_p95"] / denominator
        regional = regional.drop(columns=["_weighted_peak", "_weighted_cv", "_weighted_p95"])
        dominant = (
            by_segment.sort_values(
                ["region_id", "GeneralUseType", "building_count", "segment_id"],
                ascending=[True, True, False, True],
            )
            .drop_duplicates(["region_id", "GeneralUseType"])[
                ["region_id", "GeneralUseType", "segment_id", "model_category"]
            ]
            .rename(columns={"segment_id": "dominant_segment", "model_category": "dominant_model_category"})
        )
        regional = regional.merge(
            dominant, on=["region_id", "GeneralUseType"], how="left"
        )
        if not targets:
            dominant_counts = (
                by_segment.groupby(["region_id", "GeneralUseType"])["building_count"]
                .max()
                .rename("target_segment_buildings_dominant")
                .reset_index()
            )
            regional = regional.merge(
                dominant_counts, on=["region_id", "GeneralUseType"], how="left"
            )
            regional["target_segment_buildings"] = regional[
                "target_segment_buildings_dominant"
            ]
            regional = regional.drop(columns="target_segment_buildings_dominant")
        regional["target_segment_concentration"] = (
            regional["target_segment_buildings"] / denominator * 100
        ).fillna(0.0)
        regional["peak_intensity"] = regional.groupby(
            "GeneralUseType", dropna=False
        )["mean_peak_to_average_ratio"].transform(_minmax_100)
        regional["consumption_variability"] = regional.groupby(
            "GeneralUseType", dropna=False
        )["mean_coefficient_of_variation"].transform(_minmax_100)
        regional["priority_score"] = sum(
            regional[factor] * weight
            for factor, weight in weights.items()
        )
        regional["priority_rank"] = regional.groupby(
            "GeneralUseType", dropna=False
        )["priority_score"].rank(method="dense", ascending=False).astype(int)
        regional["priority_explanation"] = regional.apply(
            lambda row: json.dumps(
                {
                    "target_segment_concentration": {
                        "score": round(float(row["target_segment_concentration"]), 3),
                        "weight": weights["target_segment_concentration"],
                        "target_buildings": int(row["target_segment_buildings"]),
                        "target_segments": sorted(targets) if targets else "dominant segment in each region",
                    },
                    "peak_intensity": {
                        "score": round(float(row["peak_intensity"]), 3),
                        "weight": weights["peak_intensity"],
                        "observed_mean_peak_to_average": row["mean_peak_to_average_ratio"],
                    },
                    "consumption_variability": {
                        "score": round(float(row["consumption_variability"]), 3),
                        "weight": weights["consumption_variability"],
                        "observed_mean_coefficient_of_variation": row["mean_coefficient_of_variation"],
                    },
                    "method": "Weighted, min-max normalized descriptive energy indicators; not an infrastructure risk assessment.",
                },
                sort_keys=True,
            ),
            axis=1,
        )
        _write_parquet(regional, settings.output_dir / "survey_priority.parquet")
        report = {
            "coarse_region_segment_rows": len(coarse),
            "finer_region_segment_rows": len(pd.read_parquet(settings.output_dir / "region_summary_finer.parquet")),
            "survey_priority_rows": len(regional),
            "survey_priority_regions": int(regional["region_id"].nunique()),
            "weights": weights,
            "target_segments": sorted(targets),
            "priority_limitations": "Priority is based on building-consumption features only; it does not indicate transformer overload, voltage instability, or network inadequacy.",
        }
        _atomic_json(settings.reports_dir / "geospatial_summary.json", report)
        logger.info("Published segmentation geospatial outputs: %s", report)
        return report
    finally:
        con.close()
