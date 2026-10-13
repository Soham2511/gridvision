# Data pipeline

## Residential source and generated layers

Run `python -m scripts.validate_data` from the repository root. The pipeline
reads `data/raw/raw_source_snapshot.parquet` and writes:

- `data/bronze/customer_readings.parquet`: source-faithful Parquet copy.
- `data/silver/customer_interval_readings.parquet`: long-format interval
  records with missing, negative, and sampled p99.9 audit flags.
- `data/gold/customer_daily_features.parquet`: daily meter aggregates,
  notebook-aligned causal features, month-end remaining-consumption targets,
  and prediction/training eligibility flags.
- `data/gold/customer_latest_features.parquet`: latest eligible feature row
  per meter.
- `data/reports/data_profile/customer_profile.json` and `.md`,
  `data/reports/data_quality/customer_quality.json`, and
  `data/reports/lineage/customer_lineage.json`.

The current source has 140,256 timestamps, 370 meters, and 51,894,720 possible
interval readings. All timestamps are ordered and 15 minutes apart. The current
profile found no missing or negative values; zeros are retained as valid
readings. The sampled p99.9 flag is for review and does not remove readings.
Interval values already represent kWh per interval, so daily kWh is their sum
without an additional 0.25 multiplier.

The customer job is chunked for Silver writing and aggregation. Use
`--overwrite` only when intentionally replacing the generated files. The
pipeline currently creates single local Parquet outputs, not a distributed
production data lake.

## Commercial and Government dashboard inputs

Run `python -m scripts.build_dashboard_snapshots`. The script reads only the
existing Gold sources and extracts the latest `split_set == "test"` row per
entity. Commercial entities/categories are restricted to the supplied
LightGBM model's stored categorical palettes. Government `site_id_code` and
season codes are derived using the sorted site and season mappings recorded in
model metadata.

Outputs are compact local snapshots under `data/gold/dashboard/`. They are
historical replay inputs, not live or future data. The raw Commercial and
Government source datasets were not supplied.
