# Digital Tools Spend Tracker

Internal Mediseller Streamlit dashboard for tracking digital tools spend, renewals,
automation usage, AI subscriptions, and provider source health.

## Run Locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
streamlit run src/spend_tracker/dashboard/app.py
```

Copy `.env.example` to `.env` and fill provider credentials locally. Do not commit `.env`.

## Dashboard Entrypoint

```text
src/spend_tracker/dashboard/app.py
```

## Validation

```bash
python -m pytest -q
python -m ruff check .
```
