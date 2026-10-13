# Data handling

Keep original source data immutable in `raw/`; store ingestion, validated, and
business-ready outputs in `bronze/`, `silver/`, and `gold/`, respectively.
Large or sensitive production data is intentionally excluded from Git. Add
only approved, small synthetic or sanitised fixtures to `sample/`. Define data
ownership, grain, schema, units, retention, and quality rules before ingestion.
