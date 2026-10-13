# Local runbook

This is a local prototype workflow, not a production deployment.

## Prepare

1. Create a Python 3.10 environment and install `requirements-dev.txt` as
   described in the repository README.
2. Check that the trusted artifacts and supplied Gold/raw Parquet inputs are
   present. Do not load untrusted pickle files.
3. Build Residential layers with `python -m scripts.validate_data`.
4. Build Commercial/Government model-supported test replays with
   `python -m scripts.build_dashboard_snapshots`.
5. Run the focused tests and Ruff checks in the README.

## Start and verify

In separate terminals, start `python -m uvicorn app.main:app --reload` and
`python -m streamlit run dashboard\Home.py`.

Check `/api/v1/health/live`, then `/api/v1/health/ready`; readiness must list all
three model artifacts. Open Streamlit and confirm all three pages can request a
prediction. The pages must identify historical replay context and surface
invalid model outputs, service errors, and evaluation status.

## Limitations

All current model metric reports are `not_evaluated`; do not deploy as an
operational forecasting or billing service. Raw Commercial/Government data,
independent model evaluation, deployment secrets, authentication, and
production monitoring are not part of this local prototype.
