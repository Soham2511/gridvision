# Testing and quality gates

Run from the project root with the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_customer_gold.py tests\integration\test_prediction_flow.py
.\.venv\Scripts\ruff.exe check app dashboard scripts tests
```

The data-generation run additionally records row counts, timestamp cadence,
invalid/zero readings, source checksum, and layer lineage under
`data/reports/`. The FastAPI integration tests exercise checksum-verified
artifacts through startup, readiness, and prediction endpoints, and reject
missing feature values and unseen Commercial categories.

Passing application tests does not certify model quality. Each model's
evaluation report must be independently populated and reviewed before
production use; the current reports are marked `not_evaluated`.
