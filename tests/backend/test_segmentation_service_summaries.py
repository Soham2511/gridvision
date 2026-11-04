"""Tests for customer mix and regional demand summaries."""

import pandas as pd

from app.services.segmentation_service import SegmentationService
from app import create_app
from app.config import TestingConfig


def test_building_type_counts_create_nested_residential_and_other_rings() -> None:
    assignments = pd.DataFrame(
        [
            {
                "OBJECTID": 1,
                "building.type": "single-family",
                "GeneralUseType": "Residential",
                "SpecificUseType": "Single Family Residence",
                "usetype": "single_family",
            },
            {
                "OBJECTID": 2,
                "building.type": "multi-family",
                "GeneralUseType": "Residential",
                "SpecificUseType": "Apartment",
                "usetype": "multi_family",
            },
            {
                "OBJECTID": 3,
                "building.type": "institutional",
                "GeneralUseType": "Institutional",
                "SpecificUseType": "Hospital",
                "usetype": "institutional",
            },
            {
                "OBJECTID": 4,
                "building.type": "commercial",
                "GeneralUseType": "Commercial",
                "SpecificUseType": "Office",
                "usetype": "commercial",
            },
            {
                "OBJECTID": 1,
                "building.type": "single-family",
                "GeneralUseType": "Residential",
                "SpecificUseType": "Single Family Residence",
                "usetype": "single_family",
            },
        ]
    )

    counts = SegmentationService._building_type_counts(assignments)

    assert counts == [
        {"ring": "inner", "label": "Multi-family residential", "building_count": 1},
        {"ring": "inner", "label": "Single-family residential", "building_count": 1},
        {"ring": "outer", "label": "Commercial · Office", "building_count": 1},
        {"ring": "outer", "label": "Institutional · Hospital", "building_count": 1},
    ]


def test_regional_average_energy_is_weighted_by_building_count() -> None:
    regions = pd.DataFrame(
        [
            {"region_id": 1, "mean_energy_kwh": 2.0, "building_count": 3},
            {"region_id": 1, "mean_energy_kwh": 5.0, "building_count": 1},
            {"region_id": 2, "mean_energy_kwh": 4.0, "building_count": 2},
        ]
    )

    summary = SegmentationService._regional_average_energy(regions)

    assert summary == [
        {"region_id": 1, "average_energy_kwh": 2.75, "building_count": 4},
        {"region_id": 2, "average_energy_kwh": 4.0, "building_count": 2},
    ]


def test_published_segmentation_api_includes_source_version_and_period() -> None:
    client = create_app(TestingConfig).test_client()
    response = client.get("/api/v1/government/segmentation/overview")

    assert response.status_code == 200
    provenance = response.get_json()["meta"]["sourceProvenance"]
    assert provenance["sourceId"] == "segmentation_2018"
    assert provenance["dataset"] == "published_segmentation_outputs"
    assert provenance["datasetVersion"].startswith("segmentation-v1-")
    assert provenance["period"]["start"].startswith("2018-01-01")
    assert provenance["isLiveTelemetry"] is False
