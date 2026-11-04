# Data source inventory

| Source | Schema and time | Serving interface | Limits |
|---|---|---|---|
| `data/silver/customer_silver.parquet` | `OBJECTID`, `timestamp`, normalized hourly kWh; 2018 observations | `CustomerSilverHistoryService` through the household Silver retrieval tool | Cohort aggregate only for public monthly reports; data is historical and currently does not cover 2026. |
| `data/silver/commercial_silver.parquet` | `OBJECTID`, `timestamp`, normalized non-residential hourly kWh | `CommercialSilverHistoryService` through the commercial Silver retrieval tool | Per-building or authorized cohort daily rollups; historical, not live telemetry. |
| `data/gold/customer_gold.parquet` | `entity_id`, month, cutoff; monthly 2018 actual aggregates and prediction inputs | `CustomerBillPredictionService` | Historical data; estimated outputs remain predictions. |
| `data/gold/commercial_gold.parquet` | `OBJECTID`, coarse-grid key, origin/target, horizon 1–24; 2018 | `TrainedForecastProvider` bounded DuckDB reads | Target energy is historical label; not company registry data. |
| `data/airflow/government/training_ready_2018.parquet` | Grid aggregate/features by target/origin/horizon in 2018 | `TrainedForecastProvider` | Grid-level, not household data; forecast availability is conditional. |
| `data/segmentation/*.parquet` | Published assignments, profiles, regions and metadata over 2018 observation window | `SegmentationService` | Reuse outputs; do not rerun clustering. |
| `data/anomaly_prediction/synthetic_2019_normal.parquet` and saved detector | Synthetic 2019 inputs and derived findings | `AnomalyPredictionService` | Synthetic only; never verified fault or live telemetry evidence. |

No database schema, live telemetry endpoint, company profile, equipment
inventory, or operating-hours source was found. Relevant files and models are
read-only. Missing sources mean unavailable, never zero or sample substitution.
Timestamps are naive unless the source contract says otherwise. Full audited
lineage/schema details are recorded in `plan.txt`.
