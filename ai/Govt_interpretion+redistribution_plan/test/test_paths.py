from __future__ import annotations

from pathlib import Path

import pytest

from ai import paths


def test_default_paths_keep_the_existing_project_layout() -> None:
    assert paths.PROJECT_ROOT == paths.AI_DIR.parent
    assert paths.MODEL_PATH == paths.PROJECT_ROOT / "models" / "hybrid_grid_2018.joblib"
    assert paths.FORECAST_DATA_PATH == (
        paths.PROJECT_ROOT / "gold_grid_forecasting_2018.parquet"
    )
    assert paths.HISTORICAL_DATA_PATH == (
        paths.PROJECT_ROOT / "grid_level_energy.parquet"
    )
    assert paths.SIMULATIONS_DIR == paths.AI_DIR / "output"
    assert paths.ASSISTANT_OUTPUT_DIR == paths.AI_DIR / "assistant" / "output"


def test_relative_path_override_resolves_against_project_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(paths, "PROJECT_ROOT", Path("/temporary/project"))
    monkeypatch.setenv("ENERGY_MODEL_PATH", "shared/model.joblib")

    resolved = paths.configured_path(
        "ENERGY_MODEL_PATH",
        paths.PROJECT_ROOT / "models" / "default.joblib",
    )

    assert resolved == Path("/temporary/project/shared/model.joblib")


def test_project_root_can_be_relocated_with_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENERGY_PROJECT_ROOT", "/temporary/relocated-project")

    assert paths.project_root_from_environment() == Path(
        "/temporary/relocated-project"
    )


def test_absolute_path_override_is_not_rebased(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_path = Path("/shared/forecast/features.parquet")
    monkeypatch.setenv("ENERGY_FORECAST_DATA_PATH", str(custom_path))

    resolved = paths.configured_path(
        "ENERGY_FORECAST_DATA_PATH",
        paths.FORECAST_DATA_PATH,
    )

    assert resolved == custom_path
