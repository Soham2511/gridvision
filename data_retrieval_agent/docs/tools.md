# Registered tools

The registry currently exposes only service-backed capabilities:

| Tool | Existing source/service | Scope and limitations |
|---|---|---|
| `get_consumer_profile` | Customer Gold / `CustomerBillPredictionService` | Residential persona and an explicitly authorized consumer ID. |
| `get_historical_consumption` | Customer Gold or `TrainedForecastProvider` | Persona-specific history; bounded entity or explicitly granted cohort/system scope. Residential windows are monthly; commercial/government windows are daily/hourly rollups. |
| `get_latest_commercial_silver_month` | `CommercialSilverHistoryService` | Latest available Silver calendar month for an authorized commercial building or cohort; daily rollups with source provenance. |
| `get_building_details` | Commercial Gold / `TrainedForecastProvider` | Assigned building or separately authorized government building scope. Does not imply company profile/equipment/hours. |
| `get_regional_information` | Government prepared data / `TrainedForecastProvider` | Government persona; returned rows are filtered to authorized region scopes unless system-wide scope is explicitly granted. The existing catalog caps results at 100; a full system catalog is marked partial. |
| `get_energy_forecast` | Customer bill or configured trained forecast provider | Uses existing model inference only. Forecast access is exposed only when the configured model reports ready. |
| `get_anomaly_predictions` | `AnomalyPredictionService` | Explicit IDs and date range required; maximum 31 days and 20 entities per call; dates must be in 2019. All results are synthetic and not verified faults. |
| `get_segmentation_results` | `SegmentationService` | Published results only. Consumer result is owner-scoped; distributions and regional rollups require government scope. |
| `get_model_metadata` | Existing model/service metadata | Allow-listed model identifiers; no arbitrary artifact paths. |

Company-profile, equipment, and operating-hours tools are deliberately absent
because the repository has no authoritative data source for them. Adding them
requires a source inventory, owner, schema, stable identifiers, and approved
retrieval contract first.

Each tool has a strict input schema and returns the common validated output
envelope with source/provenance metadata. Registry filtering and the handler
both enforce permission/source constraints. The handler checks entity scope
before calling a data service. A model provider or data source failure is
returned as a structured tool failure and is never substituted with
`SampleDataProvider` or mock predictions.
