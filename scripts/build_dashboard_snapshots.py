"""Extract model-supported, held-out rows from the existing Gold datasets."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.dataset as ds
from app.models.registry import ModelRegistry


def _latest_test_rows(
    path: Path,
    entity_column: str,
    features: tuple[str, ...],
    target_column: str,
    supported_entities: set[str] | None = None,
) -> pd.DataFrame:
    """Stream Gold rows and retain each entity's latest test-split record."""
    required = set(features) | {entity_column, "timestamp", "split_set", target_column}
    dataset = ds.dataset(path, format="parquet")
    missing = sorted(required - set(dataset.schema.names))
    if missing:
        raise ValueError(f"{path} is missing required Gold columns: {missing}")

    predicate = ds.field("split_set") == "test"
    if supported_entities is not None:
        predicate = predicate & ds.field(entity_column).isin(sorted(supported_entities))
    latest: dict[str, dict[str, Any]] = {}
    scanner = dataset.scanner(
        columns=sorted(required),
        filter=predicate,
        batch_size=65_536,
        use_threads=True,
    )
    for record_batch in scanner.to_batches():
        frame = record_batch.to_pandas()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
        for entity, group in frame.groupby(entity_column, sort=False, observed=True):
            row = group.loc[group["timestamp"].idxmax()].to_dict()
            entity_key = str(entity)
            prior = latest.get(entity_key)
            if prior is None or row["timestamp"] > prior["timestamp"]:
                latest[entity_key] = row
    if not latest:
        return pd.DataFrame()
    result = pd.DataFrame(latest.values())
    result["evaluation_context"] = "retrospective_test_split_replay"
    return result.sort_values(entity_column).reset_index(drop=True)


def build_dashboard_snapshots(
    project_root: Path, overwrite: bool = False
) -> dict[str, int]:
    """Create small latest-test-row Parquet inputs for Commercial and Government."""
    registry = ModelRegistry(project_root)
    commercial = registry.get("commercial")
    government = registry.get("government")

    commercial_categories = commercial.estimator.booster_.pandas_categorical
    supported_buildings = {str(value) for value in commercial_categories[0]}
    commercial_frame = _latest_test_rows(
        project_root / "data" / "gold" / "building_demand.parquet",
        "building_id",
        commercial.features,
        commercial.metadata["target_name"],
        supported_buildings,
    )
    government_frame = _latest_test_rows(
        project_root / "data" / "gold" / "site_demand_cp2.parquet",
        "site_id",
        tuple(name for name in government.features if name != "site_id_code"),
        government.metadata["target_name"],
    )
    site_codes = government.metadata["categorical_encodings"]["site_id_code"]
    government_frame["site_id_code"] = government_frame["site_id"].map(site_codes)
    season_codes = government.metadata["categorical_encodings"]["season"]
    government_frame["season"] = government_frame["season"].map(season_codes)
    if government_frame["site_id_code"].isna().any():
        unsupported = (
            government_frame.loc[government_frame["site_id_code"].isna(), "site_id"]
            .astype(str)
            .unique()
        )
        raise ValueError(f"Government Gold has unsupported site IDs: {unsupported}")
    if government_frame["season"].isna().any():
        unsupported = (
            government_frame.loc[government_frame["season"].isna(), "season"]
            .astype(str)
            .unique()
        )
        raise ValueError(f"Government Gold has unsupported seasons: {unsupported}")

    outputs = {
        "commercial": commercial_frame,
        "government": government_frame,
    }
    base = project_root / "data" / "gold" / "dashboard"
    base.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, frame in outputs.items():
        destination = base / f"{name}_latest_test.parquet"
        if destination.exists() and not overwrite:
            raise FileExistsError(
                f"Dashboard snapshot exists: {destination}. Use --overwrite."
            )
        if frame.empty:
            raise ValueError(f"No supported test rows found for {name}.")
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            frame.to_parquet(
                temporary,
                index=False,
                engine="pyarrow",
                compression="zstd",
                compression_level=3,
            )
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        counts[name] = len(frame)
    return counts


def main() -> None:
    """Parse options and build the local dashboard replay files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    result = build_dashboard_snapshots(args.project_root.resolve(), args.overwrite)
    print(f"Created latest retrospective test rows: {result}")


if __name__ == "__main__":
    main()
