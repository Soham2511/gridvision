# GridVision Commercial Assistant — Sample Test Queries

Use these prompts to test the Commercial assistant from broad/general requests
through evidence-specific, forecast, renewable, multi-specialist, and schedule
optimization requests. Run each query in a fresh conversation when practical.
Record the answer, citations, selected specialists, execution trace, and any
errors.

The specialist labels below describe intended test coverage, not a guarantee
that a request can return data. Forecasts require an available trained
Commercial model and a valid building ID. RAG answers must be limited to
retrieved evidence. Renewable estimates require the inputs stated in each
query. Cost optimization requires the corresponding JSON to be pasted into the
page's **Schedule JSON** field; the assistant must not invent or infer schedule
constraints.

## General and operations retrieval

### 1. General capabilities

**Query:** Hi. What kinds of Commercial factory questions can you help with,
and what information do you need before estimating renewable generation or
optimizing a production schedule?

**Coverage:** Greeting/general workflow; no specialist required.

### 2. Broad document question

**Query:** What operational and energy information is available in the
Commercial knowledge base? Separate documented facts from generic or
demonstration material.

**Coverage:** Operations (RAG); evidence and synthetic-data handling.

### 3. Specific operational evidence

**Query:** Search the available Commercial documents for maintenance windows,
production constraints, and energy-efficiency guidance. For every finding,
identify its source and page or section when available.

**Coverage:** Operations (RAG); focused retrieval and citations.

### 4. Missing-data / hallucination check

**Query:** Which machines are currently running or stopped at my factory?
Report only machine statuses explicitly supported by the available documents;
otherwise say that current factory status is unavailable.

**Coverage:** Operations (RAG); test that the assistant does not turn
illustrative examples into live telemetry.

## Forecast and renewable specialists

### 5. Discover forecast identifiers

**Query:** Which Commercial building IDs are available for peak-demand
forecasting? Do not treat a building ID as a factory or customer identifier.

**Coverage:** Peak Prediction / building lookup; requires the forecast API,
dataset, and registered model to be available.

### 6. Single-building peak forecast

**Query:** Forecast the next supported peak-demand period for Commercial
building `[PASTE A BUILDING ID RETURNED BY QUERY 5]`. Include the forecast
window, units, timestamp, and model/data provenance. If the ID or trained model
is unavailable, explain that instead of estimating a value.

**Coverage:** Peak Prediction (single specialist); requires a valid building
ID and trained model.

### 7. Rooftop solar scenario

**Query:** Estimate a 100 kWp rooftop solar system in Bengaluru. Show
illustrative annual generation, avoided energy cost at a tariff of INR 8 per
kWh, installed cost using the configured estimate, and simple payback. State
the assumptions and clearly label the result as an estimate, not a site
measurement or quote.

**Coverage:** Renewable (single specialist); explicit capacity, location, and
tariff.

### 8. Wind scenario with explicit capacity factor

**Query:** Estimate annual generation for a 500 kW wind turbine at an explicit
30% capacity factor. Show the calculation, state that site wind measurements
have not been verified, and list what additional inputs are needed for a
project-cost or payback estimate.

**Coverage:** Renewable (single specialist); explicit capacity and capacity
factor; tests missing-cost handling.

### 9. Battery arbitrage scenario

**Query:** Estimate an illustrative battery arbitrage scenario using battery
energy capacity 100 kWh, battery discharge power 50 kW, round-trip efficiency
90%, one cycle per day, peak tariff INR 15/kWh, off-peak tariff INR 8/kWh, and
project CAPEX INR 2,000,000. Show estimated annual savings and simple payback,
explain the assumptions, and do not describe the result as guaranteed.

**Coverage:** Renewable / battery calculations (single specialist); explicit
technical, tariff, and cost inputs.

## Multi-specialist questions

### 10. Operations plus solar

**Query:** Summarize the documented factory energy-efficiency considerations
and estimate the same 100 kWp Bengaluru rooftop solar scenario at INR 8/kWh.
Keep document-backed findings separate from the solar assumptions and
calculation; do not assume the factory has a particular roof area.

**Coverage:** Operations + Renewable; tests synthesis without inventing site
details.

### 11. Operations plus peak forecast

**Query:** For Commercial building `[PASTE A VALID BUILDING ID]`, provide a
peak-demand forecast and summarize any relevant production or maintenance
constraints found in the Commercial documents. Keep forecast data and document
evidence distinct, with provenance for both.

**Coverage:** Peak Prediction + Operations; requires a valid building ID and
available forecast dependencies.

### 12. Peak forecast plus renewable scenario

**Query:** For Commercial building `[PASTE A VALID BUILDING ID]`, report the
supported peak-demand forecast and separately estimate 100 kWp rooftop solar
generation in Bengaluru at INR 8/kWh. Do not claim a quantified peak reduction
unless the available data supports that calculation.

**Coverage:** Peak Prediction + Renewable; tests bounded cross-specialist
reasoning.

## Cost optimization — primary schedule tests

For queries 13–15, paste the accompanying JSON into the webpage's
**Schedule JSON** field before sending the query. The schedule values are
fictional test inputs, not factory operating data. Compare the returned
schedule against the supplied constraints and tariffs.

### 13. Basic lowest-cost schedule

**Query:** Optimize the supplied one-job production schedule for the lowest
tariff hour. Show the selected start time and calculated cost. Do not claim
savings because no baseline schedule is supplied.

**Schedule JSON:**

```json
{
  "horizon_hours": 3,
  "prices_inr_per_kwh": [10, 2, 8],
  "jobs": [
    {
      "job_id": "batch-1",
      "machine_id": "press-1",
      "power_kw": 10,
      "duration_hours": 1,
      "release_hour": 0,
      "deadline_hour": 3
    }
  ]
}
```

**Coverage:** Cost Optimization (single specialist); validates basic schedule
inputs and no-baseline-savings behavior.

### 14. Jobs, precedence, maintenance, and baseline

**Query:** Optimize the supplied production schedule while respecting job
precedence and the press maintenance window. Compare the result only with the
explicit baseline start times in the input, and show calculated—not
guaranteed—cost and savings.

**Schedule JSON:**

```json
{
  "horizon_hours": 4,
  "prices_inr_per_kwh": [10, 2, 8, 4],
  "baseline_start_hours": {
    "press-batch": 1,
    "assembly-batch": 2
  },
  "maintenance_windows": [
    {
      "machine_id": "press-1",
      "start_hour": 0,
      "end_hour": 1
    }
  ],
  "jobs": [
    {
      "job_id": "press-batch",
      "machine_id": "press-1",
      "power_kw": 10,
      "duration_hours": 1,
      "release_hour": 0,
      "deadline_hour": 4
    },
    {
      "job_id": "assembly-batch",
      "machine_id": "assembly-1",
      "power_kw": 4,
      "duration_hours": 1,
      "release_hour": 0,
      "deadline_hour": 4,
      "predecessor_ids": ["press-batch"]
    }
  ]
}
```

**Coverage:** Cost Optimization; tests machine availability, job dependencies,
and baseline comparison.

### 15. Integrated operations, renewables, and cost optimization

**Query:** Review the supplied schedule against any relevant production or
maintenance constraints found in the Commercial documents, and optimize it
using only the tariffs, renewable-generation profile, and battery constraints
in the supplied JSON. Report document evidence separately from computed
schedule results. Do not infer missing factory data, promise savings, or claim
that the proposal controls equipment.

**Schedule JSON:**

```json
{
  "horizon_hours": 6,
  "prices_inr_per_kwh": [10, 10, 3, 3, 8, 12],
  "demand_limit_kw": 14,
  "baseline_start_hours": {
    "press-batch": 1,
    "assembly-batch": 3
  },
  "renewable_generation_kw": [0, 0, 4, 4, 0, 0],
  "maintenance_windows": [
    {
      "machine_id": "press-1",
      "start_hour": 0,
      "end_hour": 1
    }
  ],
  "jobs": [
    {
      "job_id": "press-batch",
      "machine_id": "press-1",
      "power_kw": 10,
      "duration_hours": 2,
      "release_hour": 0,
      "deadline_hour": 6
    },
    {
      "job_id": "assembly-batch",
      "machine_id": "assembly-1",
      "power_kw": 4,
      "duration_hours": 1,
      "release_hour": 0,
      "deadline_hour": 6,
      "predecessor_ids": ["press-batch"]
    }
  ],
  "battery": {
    "capacity_kwh": 10,
    "initial_soc_kwh": 5,
    "min_soc_kwh": 1,
    "max_charge_kw": 4,
    "max_discharge_kw": 4,
    "charge_efficiency": 0.95,
    "discharge_efficiency": 0.95,
    "baseline_charge_kw": [0, 0, 2, 0, 0, 0],
    "baseline_discharge_kw": [0, 0, 0, 0, 1.8, 0]
  }
}
```

**Coverage:** Operations + Cost Optimization; tests document evidence beside a
user-supplied renewable/battery schedule. The workflow does not automatically
feed the output of one specialist into another; all optimizer inputs are
provided explicitly above.