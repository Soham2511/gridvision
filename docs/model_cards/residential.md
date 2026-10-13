# Residential model card

- **Status:** Prototype artifact loaded; the current release evaluation report
  is `not_evaluated`.
- **Intended use:** Demonstration of month-end remaining-consumption inference
  for a meter with daily history. Not for billing or utility decisions.
- **Target:** `target_remaining_kwh`, kWh consumed after forecast origin through
  calendar month-end.
- **Inputs:** 27 daily/history/calendar/coverage features listed in
  `artifacts/models/residential/metadata.json`.
- **Data:** Supplied 15-minute interval readings for 370 meters, 2011-2015.
  The generated UI replay uses latest eligible input rows from December 2014.
- **Product assumptions:** Calendar-month cycle, minimum 7 elapsed days,
  minimum 90% daily interval coverage, prototype flat tariff ₹10/kWh. Interval
  kWh values are summed without multiplying by 0.25.
- **Reported performance:** The supplied artifact/notebook reports test MAE
  around 67,012 kWh and WAPE around 3.51%; the recent-rate baseline is better
  at around 43,301 kWh MAE and 2.27% WAPE. These metrics were not independently
  rerun as part of the API integration.
- **Limitations:** Model can produce negative remaining-consumption predictions
  and large outliers. The API flags negative energy as invalid and does not
  calculate a bill from it. A positive result is still an unapproved estimate.
- **Artifact:** `gridvision_month_end_model.pkl`; checksum recorded in
  `artifacts/models/residential/metadata.json`.
