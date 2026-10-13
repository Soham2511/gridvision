# Commercial model card

- **Status:** Prototype LightGBM artifact loaded; evaluation report is
  `not_evaluated`.
- **Target:** `hourly_demand_kwh`, kWh per hourly data record.
- **Inputs:** 39 features, including building/site/category, weather, calendar,
  and demand-lag/rolling fields; exact contract is in
  `artifacts/models/commercial/metadata.json`.
- **Data available:** Existing Gold dataset has 24,561,600 rows, 1,400
  buildings, and a 2016-2017 time range. Commercial raw data was not supplied.
- **Category support:** The artifact stores 29 building IDs, one site ID,
  six primary-space categories, seven sub-primary categories, and four seasons.
  Dashboard snapshot generation and API inference reject unsupported values.
- **Training uncertainty:** The notebook default sample size is 500,000 rows;
  exact executed training inputs were not confirmed. The artifact's stored
  palettes are used as the supported-category contract.
- **Evaluation:** No reviewed held-out metrics or acceptance decision are
  available. A test-split replay on the dashboard is not certification.
- **Artifact:** `building_model.pkl`; checksum recorded in
  `artifacts/models/commercial/metadata.json`.
