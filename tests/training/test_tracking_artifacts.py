from __future__ import annotations

import json
import os
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAINING_PATH = PROJECT_ROOT / "training"
if str(TRAINING_PATH) not in sys.path:
    sys.path.insert(0, str(TRAINING_PATH))

from training import train_bill_prediction as customer_training
from training.train_bill_prediction import _dataset_lineage, _model_card

AIRFLOW_CUSTOMER_PATH = PROJECT_ROOT / "airflow" / "customer"
PIPELINE_SPEC = spec_from_file_location(
    "gridvision_customer_data_pipeline",
    AIRFLOW_CUSTOMER_PATH / "data_pipeline.py",
)
if PIPELINE_SPEC is None or PIPELINE_SPEC.loader is None:
    raise RuntimeError(f"Could not load customer data pipeline from {AIRFLOW_CUSTOMER_PATH}")
data_pipeline = module_from_spec(PIPELINE_SPEC)
sys.modules[PIPELINE_SPEC.name] = data_pipeline
PIPELINE_SPEC.loader.exec_module(data_pipeline)


def _silver_fixture(path: Path) -> None:
    timestamps = pd.date_range(
        "2024-01-01 00:00:00",
        "2024-02-29 23:00:00",
        freq="h",
    )
    rows = len(timestamps)
    pd.DataFrame(
        {
            "OBJECTID": [123] * rows,
            "timestamp": timestamps,
            "normalized_building_energy_kwh": [1.25] * rows,
            "building.area.m2": [100.0] * rows,
            "FootprintArea.m2": [80.0] * rows,
            "EffectiveYearBuilt": [2000.0] * rows,
            "latitude": [40.0] * rows,
            "longitude": [-73.0] * rows,
            "idf.kw": ["residential"] * rows,
            "id.grid.coarse": [1] * rows,
            "id.grid.finer": [2.0] * rows,
            "id.tract": ["tract-1"] * rows,
            "SpecificUseType": ["single-family"] * rows,
            "building.type": ["detached"] * rows,
            "vintage": ["2000s"] * rows,
            "usetype": ["residential"] * rows,
            "GeneralUseType": ["Residential"] * rows,
        }
    ).to_parquet(path, index=False)


def _configure_data_paths(monkeypatch: pytest.MonkeyPatch, data_root: Path) -> None:
    monkeypatch.setattr(data_pipeline, "DATA_ROOT", data_root)
    log_root = data_root.parent / "logs"
    monkeypatch.setattr(data_pipeline, "LOG_ROOT", log_root)
    monkeypatch.setattr(
        data_pipeline,
        "DATASET_VERSIONS_DIR",
        data_root / "metadata" / "dataset_versions",
    )
    monkeypatch.setattr(
        data_pipeline,
        "QUALITY_REPORTS_DIR",
        log_root / "data" / "quality_reports",
    )
    monkeypatch.setattr(
        data_pipeline,
        "DUCKDB_TEMP_DIR",
        data_root / "duckdb_temp",
    )
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)


def test_gold_transform_records_quality_and_dataset_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    data_root = tmp_path / "data"
    silver_path = data_root / "silver" / "customer_silver.parquet"
    gold_path = data_root / "gold" / "customer_gold.parquet"
    silver_path.parent.mkdir(parents=True)
    _silver_fixture(silver_path)
    _configure_data_paths(monkeypatch, data_root)
    silver_versions = data_pipeline.DATASET_VERSIONS_DIR / "customer_silver"
    silver_versions.mkdir(parents=True)
    (silver_versions / "latest.json").write_text(
        json.dumps({"dataset_version": "silver-test-version"}),
        encoding="utf-8",
    )

    result = data_pipeline.build_customer_bill_gold(silver_path, gold_path)
    lineage = _dataset_lineage(gold_path)
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    report = json.loads(Path(result["quality_report"]).read_text(encoding="utf-8"))

    assert result["rows"] == 6
    assert result["quality_passed"] is True
    assert lineage["dataset_version"] == result["dataset_version"]
    assert lineage["parent_dataset_versions"] == {
        "customer_silver": "silver-test-version"
    }
    assert Path(lineage["versioned_dataset_path"]).is_file()
    assert os.path.samefile(gold_path, lineage["versioned_dataset_path"])
    assert manifest["quality_passed"] is True
    assert report["quality_checks"]["unique_entity_month_cutoff"]["passed"] is True


def test_dataset_lineage_resolves_airflow_container_paths_on_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    data_root = tmp_path / "data"
    log_root = tmp_path / "logs"
    data_path = data_root / "gold" / "customer_gold.parquet"
    version = "gold-test-version"
    versioned_path = (
        data_root
        / "metadata"
        / "dataset_versions"
        / "customer_gold"
        / f"{version}.parquet"
    )
    report_path = log_root / "data" / "quality_reports" / f"gold_{version}.json"
    latest_manifest = (
        data_root
        / "metadata"
        / "dataset_versions"
        / "customer_gold"
        / "latest.json"
    )
    for path in (data_path, versioned_path, report_path, latest_manifest):
        path.parent.mkdir(parents=True, exist_ok=True)
    data_path.touch()
    versioned_path.touch()
    report_path.touch()
    latest_manifest.write_text(
        json.dumps(
            {
                "dataset_name": "customer_gold",
                "dataset_version": version,
                "row_count": 1,
                "quality_passed": True,
                "quality_report": (
                    f"/opt/gridvision/logs/data/quality_reports/gold_{version}.json"
                ),
                "versioned_dataset_path": (
                    "/opt/gridvision/data/metadata/dataset_versions/"
                    f"customer_gold/{version}.parquet"
                ),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(customer_training, "LOG_ROOT", log_root)

    lineage = _dataset_lineage(data_path)

    assert lineage["tracked"] is True
    assert Path(lineage["quality_report"]) == report_path
    assert Path(lineage["versioned_dataset_path"]) == versioned_path


def test_failed_quality_report_is_persisted_before_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    data_root = tmp_path / "data"
    dataset_path = data_root / "bronze.parquet"
    dataset_path.parent.mkdir(parents=True)
    pq.write_table(pa.table({"value": [1]}), dataset_path)
    _configure_data_paths(monkeypatch, data_root)

    with pytest.raises(ValueError, match="quality checks failed"):
        data_pipeline._record_dataset(
            dataset_name="test_dataset",
            stage="test",
            dataset_path=dataset_path,
            row_count=1,
            quality_checks={"expected_failure": {"passed": False}},
        )

    latest = data_pipeline.DATASET_VERSIONS_DIR / "test_dataset" / "latest.json"
    report = json.loads(latest.read_text(encoding="utf-8"))
    assert report["quality_passed"] is False
    assert Path(report["versioned_dataset_path"]).is_file()
    assert Path(report["versioned_dataset_path"]).read_bytes() == dataset_path.read_bytes()


def test_model_card_includes_evaluation_and_lineage():
    card = _model_card(
        model_name="customer-bill-prediction",
        model_version="7",
        model_alias="champion",
        selected_model="hist_gradient_boosting",
        dataset={
            "dataset_version": "gold-test-version",
            "dataset_path": "/project/data/gold/customer_gold.parquet",
            "versioned_dataset_path": "/project/data/metadata/gold-test-version.parquet",
            "quality_passed": True,
            "parent_dataset_versions": {"customer_silver": "silver-test-version"},
        },
        validation_metrics={"mae_kwh": 12.3},
        test_metrics={"mae_kwh": 13.4},
        parameters={"max_iter": 80},
        run_id="mlflow-run-test",
        split_ranges={
            "train": "2024-01-01 to 2024-06-01",
            "validation": "2024-07-01 to 2024-08-01",
            "test": "2024-09-01 to 2024-10-01",
        },
    )

    assert "gold-test-version" in card
    assert "silver-test-version" in card
    assert "13.4" in card
    assert "illustrative" in card
