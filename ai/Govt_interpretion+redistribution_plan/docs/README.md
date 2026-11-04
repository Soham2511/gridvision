# AI workspace documentation

This documentation covers only the additional work in `ai/`; the existing
forecasting project and trained model artifacts remain unchanged.

- [Architecture and data flow](../assistant/ARCHITECTURE.md)
- [Runnable example questions](./QUERY_EXAMPLES.md)
- [Provider and model integration contract](./PROVIDER_INTEGRATION.md)
- [Assistant setup and CLI](../assistant/README.md)
- [Forecasting and synthetic redistribution pipeline](../README.md)

The assistant reads generated plan JSON as its source of truth. Forecast demand
is model-predicted; supply, network edges, capacities, transfer suggestions,
and transmission losses are synthetic assumptions, not actual infrastructure
or measurements.
