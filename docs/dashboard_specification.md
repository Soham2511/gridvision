# Dashboard specification

The multipage Streamlit app is under `dashboard/` and calls FastAPI using the
shared client in `dashboard/clients/api_client.py`.

- **Residential:** Select a meter and replay its latest eligible daily Gold
  feature row. Shows actual month-to-date kWh, raw model output, the
  retrospective observed remaining target, a bill estimate only when the
  prediction is physically valid, coverage, and prototype-tariff caveats.
- **Commercial:** Select a supported building and compare its latest held-out
  test-split Gold value with the model prediction for that same hourly record.
- **Government:** Select a site and compare the latest held-out test-split
  value with its model prediction. No redistribution recommendation is implied.
- **Historical analysis:** Shows Residential daily consumption, target, and
  coverage from the generated Gold layer.
- **Data and model health:** Shows API readiness, customer data quality, model
  checksums, feature counts, and evaluation report statuses.

The Residential source ends in 2015; Commercial and Government Gold data ends
in 2017. All pages identify these outputs as historical replays. The Commercial
page only offers categories the artifact supports. Connection, HTTP, and
missing-data errors are shown instead of being replaced with stale or example
predictions.
