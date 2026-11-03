from pathlib import Path

from training.customer_segmentation.config import SegmentationSettings


def test_segmentation_settings_read_artifact_paths_from_environment(
    monkeypatch, tmp_path: Path
) -> None:
    paths = {
        "SEGMENTATION_SOURCE_PATH": tmp_path / "source.parquet",
        "SEGMENTATION_OUTPUT_DIR": tmp_path / "published",
        "SEGMENTATION_FEATURE_PATH": tmp_path / "gold" / "features.parquet",
        "SEGMENTATION_MODEL_DIR": tmp_path / "models" / "segmentation",
        "SEGMENTATION_REPORTS_DIR": tmp_path / "docs" / "reports",
    }
    for name, path in paths.items():
        monkeypatch.setenv(name, str(path))

    settings = SegmentationSettings.from_environment()

    assert settings.source_path == paths["SEGMENTATION_SOURCE_PATH"]
    assert settings.output_dir == paths["SEGMENTATION_OUTPUT_DIR"]
    assert settings.feature_path == paths["SEGMENTATION_FEATURE_PATH"]
    assert settings.model_dir == paths["SEGMENTATION_MODEL_DIR"]
    assert settings.reports_dir == paths["SEGMENTATION_REPORTS_DIR"]


def test_segmentation_settings_default_to_project_artifact_layout(
    tmp_path: Path,
) -> None:
    settings = SegmentationSettings(
        source_path=tmp_path / "source.parquet",
        output_dir=tmp_path / "published",
    )

    assert settings.feature_path.name == "customer_segmentation_features.parquet"
    assert settings.feature_path.parent.parts[-2:] == ("data", "gold")
    assert settings.model_dir.parts[-2:] == ("models", "segmentation")
    assert settings.reports_dir.parts[-2:] == ("customer_segmentation", "reports")
