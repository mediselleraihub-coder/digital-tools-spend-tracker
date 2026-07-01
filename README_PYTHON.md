# Python Foundation

This phase builds connectivity and ingestion foundations before any dashboard work.

```bash
cd "/Users/shivam/Work/Mediseller/Digital Tools Spend Tracker"
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run provider source classification:

```bash
spend-tracker status
```

Run connectivity checks:

```bash
spend-tracker check
```

Run one provider:

```bash
spend-tracker check --provider supabase
spend-tracker check --provider n8n_cloud
spend-tracker check --provider omnidimension
```

Notebook entrypoint:

```bash
jupyter lab notebooks/00_connectivity_checks.ipynb
```

The notebook imports package code. Do not put provider credentials, API logic, or ingestion
logic directly in notebook cells.

## Pre-Supabase dashboard

This dashboard does not require Supabase. It shows manual subscriptions/assets from
`config/manual_items.yml`, safe subscription values from `.env`, and live n8n/OmniDimension
API snapshots.

```bash
streamlit run src/spend_tracker/dashboard/app.py
```
