# Peak Prediction Skill

## Purpose
Use the peak prediction specialist for demand, load, peak-period, tariff, or
energy-cost questions that require an existing Commercial building forecast.

## Select this skill when
- The user asks for a load or peak-demand forecast, forecast history, or model
  and dataset provenance.
- Forecast relevance is explicit in the current request or needed to interpret
  a short follow-up in the recent conversation.

## Constraints
- Require an explicit supported Commercial `building_id`; never infer one from
  a factory, site name, or conversation.
- Treat the forecast as a historical replay, not live telemetry.
- Do not invent a forecast, data coverage, or provenance when the tool reports
  the model or dataset unavailable.
- Use only the registered `peak_forecast` capability.
