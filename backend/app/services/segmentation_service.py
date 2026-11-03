"""Read-only access to the published Government segmentation outputs."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from app.api.error_handlers import AppError
from app.models.registry import MODEL_REGISTRY
from training.customer_segmentation.config import SegmentationSettings
from training.customer_segmentation.pipeline import validate_outputs


class SegmentationUnavailableError(AppError):
    """Published segmentation outputs are incomplete or unavailable."""

    def __init__(self, message: str = "Government customer segmentation is unavailable.") -> None:
        super().__init__(message, code="SEGMENTATION_UNAVAILABLE", status_code=503)


class SegmentationService:
    """Serve the latest complete segmentation output set without training models."""

    PERIOD_FILES = {
        "hourly": "cluster_hourly_profile.parquet",
        "daily": "cluster_daily_profile.parquet",
        "monthly": "cluster_monthly_profile.parquet",
    }
    REGION_FILES = {
        "coarse": ("region_summary_coarse.parquet", "id.grid.coarse"),
        "finer": ("region_summary_finer.parquet", "id.grid.finer"),
    }

    def __init__(
        self,
        output_dir: str | Path,
        max_page_size: int = 200,
        reports_dir: str | Path | None = None,
    ) -> None:
        self.output_dir = Path(output_dir).expanduser()
        self.reports_dir = (
            Path(reports_dir).expanduser()
            if reports_dir is not None
            else self.output_dir / "reports"
        )
        self.max_page_size = max(1, int(max_page_size))

    def _ensure_ready(self) -> dict[str, Any]:
        try:
            return validate_outputs(
                replace(
                    SegmentationSettings.from_environment(),
                    output_dir=self.output_dir,
                    reports_dir=self.reports_dir,
                )
            )
        except (OSError, ValueError, KeyError) as exc:
            raise SegmentationUnavailableError(
                "Published Government segmentation outputs are missing or incomplete."
            ) from exc

    def _json(self, filename: str) -> dict[str, Any]:
        self._ensure_ready()
        path = (
            self.reports_dir / filename.removeprefix("reports/")
            if filename.startswith("reports/")
            else self.output_dir / filename
        )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SegmentationUnavailableError(
                f"Published segmentation metadata is unavailable: {filename}."
            ) from exc

    def _frame(self, filename: str) -> pd.DataFrame:
        self._ensure_ready()
        try:
            return pd.read_parquet(self.output_dir / filename)
        except (OSError, ValueError, ImportError) as exc:
            raise SegmentationUnavailableError(
                f"Published segmentation table is unavailable: {filename}."
            ) from exc

    @staticmethod
    def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
        # pandas JSON conversion normalizes NumPy scalars and turns NaN into null.
        return json.loads(frame.to_json(orient="records", date_format="iso"))

    def _category(self, category: str | None) -> str | None:
        if category is None:
            return None
        counts = self._json("model_metadata.json").get("category_building_counts", {})
        canonical = {str(value).casefold(): str(value) for value in counts}
        result = canonical.get(category.casefold())
        if result is None:
            raise AppError(
                f"Unknown segmentation category '{category}'.",
                code="INVALID_INPUT",
                status_code=422,
                details={"allowed": sorted(counts)},
            )
        return result

    def _segment(self, segment_id: str | None) -> str | None:
        if segment_id is None:
            return None
        profiles = self._frame("cluster_profiles.parquet")
        existing = set(profiles["segment_id"].astype(str))
        if segment_id not in existing:
            raise AppError(
                f"Unknown segmentation segment '{segment_id}'.",
                code="INVALID_INPUT",
                status_code=422,
            )
        return segment_id

    def _region_id(self, level: str, value: str | None) -> int | float | None:
        if value is None:
            return None
        if level not in self.REGION_FILES:
            raise AppError(
                "region_level must be 'coarse' or 'finer'.",
                code="INVALID_INPUT",
                status_code=422,
            )
        try:
            number = float(value)
        except ValueError as exc:
            raise AppError(
                "region_id must be numeric for the selected region level.",
                code="INVALID_INPUT",
                status_code=422,
            ) from exc
        if not pd.notna(number) or not number.is_integer():
            raise AppError(
                "region_id must be a finite integer-valued identifier.",
                code="INVALID_INPUT",
                status_code=422,
            )
        return int(number) if level == "coarse" else float(number)

    def _page(self, page: int, page_size: int) -> tuple[int, int]:
        if page < 1:
            raise AppError("page must be at least 1.", code="INVALID_INPUT", status_code=422)
        if page_size < 1 or page_size > self.max_page_size:
            raise AppError(
                f"page_size must be between 1 and {self.max_page_size}.",
                code="INVALID_INPUT",
                status_code=422,
            )
        return page, page_size

    def _filter_frame(
        self,
        frame: pd.DataFrame,
        category: str | None,
        segment_id: str | None,
    ) -> pd.DataFrame:
        if category is not None:
            if "GeneralUseType" in frame:
                frame = frame[frame["GeneralUseType"] == category]
            elif "model_category" in frame:
                frame = frame[frame["model_category"] == category]
        if segment_id is not None and "segment_id" in frame:
            frame = frame[frame["segment_id"] == segment_id]
        return frame

    def _paginate(
        self, frame: pd.DataFrame, page: int, page_size: int, sort_by: str
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        page, page_size = self._page(page, page_size)
        frame = frame.sort_values(sort_by, kind="stable")
        total = len(frame)
        start = (page - 1) * page_size
        records = self._records(frame.iloc[start : start + page_size])
        return records, {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        }

    def get_overview(self) -> dict[str, Any]:
        metadata = self._json("model_metadata.json")
        features = self._json("reports/feature_generation.json")
        distribution = self._frame("segment_distribution.parquet")
        geo = self._json("reports/geospatial_summary.json")
        assignments = self._frame("consumer_assignments.parquet")
        coarse_regions = self._frame("region_summary_coarse.parquet")
        return {
            "model_version": metadata.get("model_version"),
            "observation_start": features.get("observation_start"),
            "observation_end_exclusive": features.get("observation_end_exclusive"),
            "eligible_buildings": features.get("eligible_buildings"),
            "assigned_buildings": metadata.get("assignment_count"),
            "unassigned_buildings": metadata.get("unassigned_feature_buildings"),
            "category_building_counts": metadata.get("category_building_counts", {}),
            "building_type_counts": self._building_type_counts(assignments),
            "regional_average_energy": self._regional_average_energy(coarse_regions),
            "segments": self._records(distribution),
            "region_counts": {
                "coarse_segment_rows": geo.get("coarse_region_segment_rows"),
                "finer_segment_rows": geo.get("finer_region_segment_rows"),
                "survey_priority_regions": geo.get(
                    "survey_priority_regions", geo.get("survey_priority_rows")
                ),
            },
        }

    def get_model_status(self) -> dict[str, Any]:
        definition = MODEL_REGISTRY["government-customer-segmentation"].as_dict()
        try:
            validation = self._ensure_ready()
            metadata = json.loads(
                (self.output_dir / "model_metadata.json").read_text(
                    encoding="utf-8"
                )
            )
            profile = json.loads(
                (self.output_dir / "reports" / "source_profile.json").read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError, SegmentationUnavailableError) as exc:
            return {
                **definition,
                "status": "unavailable",
                "provider": "published_artifacts",
                "modelVersion": "not_deployed",
                "selectedModel": "not_deployed",
                "runSummary": "Published segmentation outputs are unavailable.",
                "error": str(exc),
            }

        model_count = len(metadata.get("trained_models", []))
        assignment_count = int(validation["assignment_count"])
        sample_fraction = profile.get("building_sample_fraction")
        sample_summary = (
            f" · {sample_fraction:.0%} deterministic building sample"
            if isinstance(sample_fraction, (int, float))
            else ""
        )
        return {
            **definition,
            "status": "configured",
            "provider": "published_artifacts",
            "modelVersion": str(metadata.get("model_version") or "unknown"),
            "selectedModel": f"{model_count} category models",
            "runSummary": (
                f"{assignment_count:,} building assignments across "
                f"{model_count} category models{sample_summary}"
            ),
        }

    @staticmethod
    def _building_type_counts(assignments: pd.DataFrame) -> list[dict[str, Any]]:
        buildings = assignments.drop_duplicates("OBJECTID").copy()
        specific_use = buildings.get(
            "SpecificUseType", pd.Series(index=buildings.index, dtype="object")
        )
        fallback_type = buildings.get(
            "building.type", pd.Series(index=buildings.index, dtype="object")
        )
        general_type = buildings.get(
            "GeneralUseType", pd.Series(index=buildings.index, dtype="object")
        )
        building_type = buildings.get(
            "building.type", pd.Series(index=buildings.index, dtype="object")
        ).fillna("").astype(str).str.strip().str.casefold()
        use_type = buildings.get(
            "usetype", pd.Series(index=buildings.index, dtype="object")
        ).fillna("").astype(str).str.strip().str.casefold()
        general_type = general_type.fillna("").astype(str).str.strip()
        specific_use = (
            specific_use.fillna("").astype(str).str.strip()
            .replace("", pd.NA)
            .fillna(fallback_type.fillna("").astype(str).str.strip())
            .replace("", pd.NA)
            .fillna(general_type)
            .replace("", "Unspecified")
        )
        is_residential = general_type.str.casefold().eq("residential")
        is_single_family = building_type.eq("single-family") | use_type.isin(
            {"single_family", "single-family"}
        )
        is_multi_family = building_type.eq("multi-family") | use_type.isin(
            {"multi_family", "multi-family"}
        )
        residential_group = pd.Series("Other residential", index=buildings.index)
        residential_group.loc[is_single_family] = "Single-family residential"
        residential_group.loc[is_multi_family] = "Multi-family residential"

        grouped = pd.DataFrame(
            {
                "ring": "outer",
                "label": general_type + " · " + specific_use,
            },
            index=buildings.index,
        )
        grouped.loc[is_residential, "ring"] = "inner"
        grouped.loc[is_residential, "label"] = residential_group.loc[is_residential]
        counts = (
            grouped.groupby(["ring", "label"], sort=False)
            .size()
            .rename("building_count")
            .reset_index()
        )
        counts["ring_order"] = counts["ring"].map({"inner": 0, "outer": 1})
        counts = counts.sort_values(
            ["ring_order", "building_count", "label"],
            ascending=[True, False, True],
            kind="stable",
        )
        return [
            {
                "ring": row.ring,
                "label": row.label,
                "building_count": int(row.building_count),
            }
            for row in counts.itertuples(index=False)
        ]

    @staticmethod
    def _regional_average_energy(regions: pd.DataFrame) -> list[dict[str, Any]]:
        values = regions.copy()
        values["mean_energy_kwh"] = pd.to_numeric(
            values["mean_energy_kwh"], errors="coerce"
        )
        values["building_count"] = pd.to_numeric(
            values["building_count"], errors="coerce"
        )
        values = values.dropna(subset=["region_id", "mean_energy_kwh", "building_count"])
        values = values[values["building_count"] > 0]
        weighted = values.assign(
            weighted_energy=values["mean_energy_kwh"] * values["building_count"]
        )
        summary = (
            weighted.groupby("region_id", as_index=False)
            .agg(
                weighted_energy=("weighted_energy", "sum"),
                building_count=("building_count", "sum"),
            )
            .sort_values("region_id", kind="stable")
        )
        summary["average_energy_kwh"] = (
            summary["weighted_energy"] / summary["building_count"]
        )
        return [
            {
                "region_id": row.region_id,
                "average_energy_kwh": float(row.average_energy_kwh),
                "building_count": int(row.building_count),
            }
            for row in summary.itertuples(index=False)
        ]

    def get_profiles(self, category: str | None = None) -> list[dict[str, Any]]:
        category = self._category(category)
        frame = self._frame("cluster_profiles.parquet")
        if category is not None:
            assignments = self._frame("consumer_assignments.parquet")
            segment_ids = assignments.loc[
                assignments["GeneralUseType"] == category, "segment_id"
            ].dropna().unique()
            frame = frame[frame["segment_id"].isin(segment_ids)]
        return self._records(frame.sort_values("segment_id", kind="stable"))

    def get_distribution(self, category: str | None = None) -> list[dict[str, Any]]:
        category = self._category(category)
        assignments = self._frame("consumer_assignments.parquet")
        if category is not None:
            assignments = assignments[assignments["GeneralUseType"] == category]
        assignments = assignments.dropna(subset=["segment_id"])
        total = max(1, assignments["OBJECTID"].nunique())
        frame = (
            assignments.groupby(
                ["GeneralUseType", "segment_id", "model_category"], dropna=False
            )
            .agg(building_count=("OBJECTID", "nunique"))
            .reset_index()
        )
        frame["share_of_assigned_buildings"] = frame["building_count"] / total
        return self._records(
            frame.sort_values(
                ["GeneralUseType", "segment_id"], kind="stable"
            )
        )

    def get_time_series(
        self, segment_id: str, period: str, category: str | None = None
    ) -> list[dict[str, Any]]:
        segment_id = self._segment(segment_id) or segment_id
        category = self._category(category)
        filename = self.PERIOD_FILES.get(period)
        if filename is None:
            raise AppError(
                "period must be one of hourly, daily, or monthly.",
                code="INVALID_INPUT",
                status_code=422,
                details={"allowed": sorted(self.PERIOD_FILES)},
            )
        frame = self._frame(filename)
        frame = self._filter_frame(frame, category, segment_id)
        return self._records(frame.sort_values("period_index", kind="stable"))

    def get_regions(
        self,
        level: str,
        category: str | None,
        segment_id: str | None,
        region_id: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        descriptor = self.REGION_FILES.get(level)
        if descriptor is None:
            raise AppError(
                "level must be 'coarse' or 'finer'.",
                code="INVALID_INPUT",
                status_code=422,
                details={"allowed": sorted(self.REGION_FILES)},
            )
        filename, _ = descriptor
        category = self._category(category)
        segment_id = self._segment(segment_id)
        parsed_region = self._region_id(level, region_id)
        frame = self._filter_frame(self._frame(filename), category, segment_id)
        if parsed_region is not None:
            frame = frame[frame["region_id"] == parsed_region]
        return self._paginate(frame, page, page_size, "region_id")

    def get_region_detail(
        self, level: str, region_id: str, category: str | None = None
    ) -> dict[str, Any]:
        category = self._category(category)
        items, _ = self.get_regions(
            level, category, None, region_id, 1, self.max_page_size
        )
        if not items:
            raise AppError(
                f"No segmentation detail exists for {level} region '{region_id}'.",
                code="NOT_FOUND",
                status_code=404,
            )
        parsed_region = self._region_id(level, region_id)
        priority = None
        if level == "coarse":
            priorities = self._frame("survey_priority.parquet")
            matched = priorities[priorities["region_id"] == parsed_region]
            if category is not None:
                category_column = (
                    "GeneralUseType"
                    if "GeneralUseType" in matched
                    else "dominant_model_category"
                )
                matched = matched[matched[category_column] == category]
            if not matched.empty:
                priority = self._records(matched.iloc[:1])[0]
                explanation = priority.get("priority_explanation")
                if explanation:
                    try:
                        priority["priority_explanation"] = json.loads(explanation)
                    except (TypeError, json.JSONDecodeError):
                        pass
        return {"level": level, "region_id": parsed_region, "segments": items, "survey_priority": priority}

    def get_assignments(
        self,
        category: str | None,
        segment_id: str | None,
        region_level: str,
        region_id: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        descriptor = self.REGION_FILES.get(region_level)
        if descriptor is None:
            raise AppError(
                "region_level must be 'coarse' or 'finer'.",
                code="INVALID_INPUT",
                status_code=422,
                details={"allowed": sorted(self.REGION_FILES)},
            )
        _, assignment_region_column = descriptor
        category = self._category(category)
        segment_id = self._segment(segment_id)
        parsed_region = self._region_id(region_level, region_id)
        frame = self._filter_frame(
            self._frame("consumer_assignments.parquet"), category, segment_id
        )
        if parsed_region is not None:
            frame = frame[frame[assignment_region_column] == parsed_region]
        return self._paginate(frame, page, page_size, "OBJECTID")

    def get_priorities(
        self, category: str | None, page: int, page_size: int
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        category = self._category(category)
        frame = self._frame("survey_priority.parquet")
        if category is not None:
            category_column = (
                "GeneralUseType"
                if "GeneralUseType" in frame
                else "dominant_model_category"
            )
            frame = frame[frame[category_column] == category]
        records, meta = self._paginate(frame, page, page_size, "priority_rank")
        for record in records:
            explanation = record.get("priority_explanation")
            if explanation:
                try:
                    record["priority_explanation"] = json.loads(explanation)
                except (TypeError, json.JSONDecodeError):
                    pass
        return records, meta

    def get_model_metadata(self) -> dict[str, Any]:
        metadata = self._json("model_metadata.json")
        for key in ("source_feature_table",):
            metadata.pop(key, None)
        for model in metadata.get("trained_models", []):
            model.pop("model_path", None)
        return metadata
