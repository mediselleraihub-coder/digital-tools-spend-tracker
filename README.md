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

## Deployment

Recommended MVP path: deploy the private GitHub repo to Render using the included
`render.yaml` blueprint or the included `Dockerfile`.

Required hosting secrets:

- `SUPABASE_DB_PASSWORD`
- `N8N_API_KEY`
- `OMNIDIMENSION_API_KEY`
- `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` only if REST/service-role
  workflows are enabled
- Google BigQuery billing export variables when Gemini billing ingestion is enabled

Local Docker smoke test:

```bash
docker build -t digital-tools-spend-tracker .
docker run --rm -p 8501:8501 --env-file .env digital-tools-spend-tracker
```

Then open `http://127.0.0.1:8501`.
