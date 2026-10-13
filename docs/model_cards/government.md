# Government model card

- **Status:** Prototype LightGBM artifact loaded; evaluation report is
  `not_evaluated`.
- **Target:** `total_demand_kwh`, kWh per hourly data record at site level.
- **Inputs:** 27 features; exact contract and numeric site/season encoding are
  recorded in `artifacts/models/government/metadata.json`.
- **Data available:** Existing Gold dataset has 298,248 rows, 17 sites, and a
  2016-2017 time range. Government raw data was not supplied.
- **Site encoding:** Alphabetically sorted site IDs map to codes 0-16;
  seasons map Fall=0, Spring=1, Summer=2, Winter=3.
- **Evaluation:** No reviewed held-out metrics or acceptance decision are
  available. The dashboard compares a model output with a historical test-split
  row only; this is not an evaluation report.
- **Limitations:** Prediction does not perform demand redistribution, grid
  optimization, or operational recommendations.
- **Artifact:** `regional_model.pkl`; checksum recorded in
  `artifacts/models/government/metadata.json`.
