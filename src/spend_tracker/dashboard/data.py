from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import psycopg
import yaml
from google.cloud import bigquery
from google.oauth2 import service_account

from spend_tracker.config import PROJECT_ROOT, Settings
from spend_tracker.provider_status import classify_providers

MANUAL_ITEMS_PATH = PROJECT_ROOT / "config" / "manual_items.yml"
N8N_EXECUTION_PAGE_LIMIT = 100
N8N_EXECUTION_MAX_PAGES = 100


@dataclass(frozen=True)
class ApiSnapshot:
    provider: str
    status: str
    summary: dict[str, Any]
    records: dict[str, pd.DataFrame]
    error: str | None = None


@dataclass(frozen=True)
class PersistenceStatus:
    status: str
    message: str
    detail: dict[str, Any]


def load_manual_registry(path: Path = MANUAL_ITEMS_PATH) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {
            "manual_subscriptions": [],
            "manual_assets": [],
            "manual_usage_markers": [],
        }
    with path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file) or {}
    return {
        "manual_subscriptions": list(payload.get("manual_subscriptions") or []),
        "manual_assets": list(payload.get("manual_assets") or []),
        "manual_usage_markers": list(payload.get("manual_usage_markers") or []),
        "planning_fx_rates": list(payload.get("planning_fx_rates") or []),
    }


def planning_fx_dataframe() -> pd.DataFrame:
    frame = pd.DataFrame(load_manual_registry()["planning_fx_rates"])
    if frame.empty:
        return pd.DataFrame(
            [{"currency_code": "INR", "to_currency_code": "INR", "fx_rate": Decimal("1")}]
        )
    frame["fx_rate"] = frame["fx_rate"].map(_to_decimal)
    frame["rate_date"] = pd.to_datetime(frame["rate_date"], errors="coerce").dt.date
    return frame


def manual_subscriptions_dataframe(settings: Settings) -> pd.DataFrame:
    registry_rows = load_manual_registry()["manual_subscriptions"]
    env_rows = [
        {
            "provider": "openai",
            "category": "AI Subscription",
            "product": "ChatGPT Plus",
            "plan": settings.openai_plan_name,
            "billing_cycle": "monthly",
            "amount": settings.openai_monthly_cost,
            "currency_code": "INR",
            "renewal_date": settings.openai_renewal_date,
            "source": "env",
            "status": "active",
        },
        {
            "provider": "anthropic",
            "category": "AI Subscription",
            "product": "Claude Pro",
            "plan": settings.anthropic_plan_name,
            "billing_cycle": "monthly",
            "amount": settings.anthropic_monthly_cost,
            "currency_code": "USD",
            "renewal_date": settings.anthropic_renewal_date,
            "source": "env",
            "status": "active",
        },
        {
            "provider": "n8n_cloud",
            "category": "Automation",
            "product": "n8n Cloud",
            "plan": "Cloud workspace",
            "billing_cycle": "monthly",
            "amount": settings.n8n_monthly_cost,
            "currency_code": "EUR",
            "renewal_date": settings.n8n_renewal_date,
            "source": "env",
            "status": "active",
        },
        {
            "provider": "higgsfield_ai",
            "category": "AI Creative",
            "product": "Higgsfield AI",
            "plan": settings.higgsfield_plan_name,
            "billing_cycle": "monthly",
            "amount": settings.higgsfield_monthly_cost,
            "currency_code": settings.higgsfield_currency_code,
            "renewal_date": settings.higgsfield_renewal_date,
            "source": "env",
            "status": "active",
        },
    ]
    registry_by_provider = {row.get("provider"): row for row in registry_rows}
    rows = []
    for row in env_rows:
        if row["amount"]:
            rows.append(row)
        elif row["provider"] in registry_by_provider:
            rows.append(registry_by_provider[row["provider"]])
    for row in registry_rows:
        if row.get("provider") not in {item["provider"] for item in rows}:
            rows.append(row)

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame["amount"] = frame["amount"].map(_to_decimal)
    frame["monthly_equivalent"] = frame.apply(_monthly_equivalent, axis=1)
    frame["renewal_date"] = pd.to_datetime(frame["renewal_date"], errors="coerce").dt.date
    frame["days_to_renewal"] = frame["renewal_date"].map(_days_until)
    return frame.sort_values(["renewal_date", "provider"], na_position="last")


def manual_assets_dataframe() -> pd.DataFrame:
    frame = pd.DataFrame(load_manual_registry()["manual_assets"])
    if frame.empty:
        return frame

    for column in ["annual_amount", "monthly_amount"]:
        if column in frame:
            frame[column] = frame[column].map(_to_decimal)
    frame["renewal_date"] = pd.to_datetime(frame["renewal_date"], errors="coerce").dt.date
    frame["days_to_renewal"] = frame["renewal_date"].map(_days_until)
    return frame.sort_values(["renewal_date", "provider", "asset_type"], na_position="last")


def usage_markers_dataframe() -> pd.DataFrame:
    return pd.DataFrame(load_manual_registry()["manual_usage_markers"])


def combined_commitments_dataframe(
    subscriptions: pd.DataFrame,
    assets: pd.DataFrame,
    fx_rates: pd.DataFrame,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not subscriptions.empty:
        sub_frame = subscriptions.copy()
        sub_frame["record_type"] = "subscription"
        sub_frame["name"] = sub_frame["product"]
        sub_frame["monthly_amount"] = sub_frame["monthly_equivalent"]
        frames.append(
            sub_frame[
                [
                    "record_type",
                    "provider",
                    "category",
                    "product",
                    "name",
                    "billing_cycle",
                    "monthly_amount",
                    "amount",
                    "currency_code",
                    "renewal_date",
                    "days_to_renewal",
                    "status",
                ]
            ]
        )

    if not assets.empty:
        asset_frame = assets.copy()
        asset_frame["record_type"] = "asset"
        asset_frame["name"] = asset_frame["asset_name"]
        asset_frame["amount"] = asset_frame.get(
            "monthly_amount",
            pd.Series(index=asset_frame.index),
        )
        if "annual_amount" in asset_frame:
            annual_monthly = asset_frame["annual_amount"].map(
                lambda value: value / Decimal("12") if isinstance(value, Decimal) else None
            )
            asset_frame["monthly_amount"] = asset_frame.get(
                "monthly_amount", pd.Series(index=asset_frame.index)
            ).combine_first(annual_monthly)
            asset_frame["amount"] = asset_frame["monthly_amount"]
        asset_frame["billing_cycle"] = "asset"
        if "auto_renew" not in asset_frame:
            asset_frame["auto_renew"] = None
        frames.append(
            asset_frame[
                [
                    "record_type",
                    "provider",
                    "category",
                    "product",
                    "name",
                    "billing_cycle",
                    "monthly_amount",
                    "amount",
                    "currency_code",
                    "renewal_date",
                    "days_to_renewal",
                    "auto_renew",
                    "status",
                ]
            ]
        )

    if not frames:
        return pd.DataFrame()

    commitments = pd.concat(frames, ignore_index=True)
    if "auto_renew" not in commitments:
        commitments["auto_renew"] = None
    fx_map = {
        row["currency_code"]: row["fx_rate"]
        for _, row in fx_rates.iterrows()
        if row.get("currency_code") and row.get("fx_rate") is not None
    }
    commitments["fx_rate_to_inr"] = commitments["currency_code"].map(fx_map)
    commitments["monthly_inr"] = commitments.apply(_amount_to_inr, axis=1)
    return commitments


def provider_status_dataframe(settings: Settings) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "provider": status.provider,
            "status": status.status.value,
            "reason": status.reason,
        }
        for status in classify_providers(settings)
    )


def check_supabase_persistence(settings: Settings) -> PersistenceStatus:
    url_project_ref = _project_ref_from_supabase_url(str(settings.supabase_url))
    db_user_project_ref = _project_ref_from_pooler_user(settings.supabase_db_user)
    warnings = []
    if url_project_ref and db_user_project_ref and url_project_ref != db_user_project_ref:
        warnings.append(
            "SUPABASE_URL project ref and SUPABASE_DB_USER project ref do not match"
        )

    detail = {
        "db_host": settings.supabase_db_host,
        "db_port": settings.supabase_db_port,
        "db_name": settings.supabase_db_name,
        "db_user": settings.supabase_db_user,
        "url_project_ref": url_project_ref,
        "db_user_project_ref": db_user_project_ref,
        "warnings": warnings,
    }

    try:
        with psycopg.connect(
            host=settings.supabase_db_host,
            port=settings.supabase_db_port,
            dbname=settings.supabase_db_name,
            user=settings.supabase_db_user,
            password=settings.supabase_db_password.get_secret_value(),
            sslmode="require",
            connect_timeout=8,
        ) as conn, conn.cursor() as cur:
            cur.execute("select 1")
            cur.fetchone()
        if warnings:
            return PersistenceStatus(
                status="warning",
                message="Supabase DB connected, but config mismatch warning exists",
                detail=detail,
            )
        return PersistenceStatus(
            status="connected",
            message="Supabase DB connected",
            detail=detail,
        )
    except Exception as exc:
        detail["error"] = f"{exc.__class__.__name__}: {exc}"
        return PersistenceStatus(
            status="not_connected",
            message="Supabase DB not connected",
            detail=detail,
        )


def fetch_n8n_snapshot(settings: Settings) -> ApiSnapshot:
    if not settings.n8n_base_url or not settings.n8n_api_key:
        return ApiSnapshot("n8n_cloud", "skipped", {}, {}, "N8N_BASE_URL or N8N_API_KEY missing")

    base_url = str(settings.n8n_base_url).rstrip("/")
    headers = {"X-N8N-API-KEY": settings.n8n_api_key.get_secret_value()}
    try:
        with httpx.Client(timeout=20, headers=headers) as client:
            workflows_response = client.get(f"{base_url}/api/v1/workflows", params={"limit": "100"})
            workflows_response.raise_for_status()
            workflows_payload = workflows_response.json()

            executions_payload: dict[str, Any] = {"data": []}
            executions_error = None
            executions_response = client.get(
                f"{base_url}/api/v1/executions",
                params={"limit": str(N8N_EXECUTION_PAGE_LIMIT)},
            )
            if executions_response.status_code == 200:
                executions_payload = executions_response.json()
            else:
                executions_error = f"executions endpoint returned {executions_response.status_code}"
            usage_summary = _fetch_n8n_current_month_usage(client, base_url, settings)

        workflows = _payload_records(workflows_payload)
        executions = _payload_records(executions_payload)
        workflows_frame = pd.DataFrame(workflows)
        executions_frame = pd.DataFrame(executions)

        active_count = 0
        if not workflows_frame.empty and "active" in workflows_frame:
            active_count = int(workflows_frame["active"].fillna(False).sum())

        summary = {
            "workflows_sampled": len(workflows_frame),
            "active_workflows_sampled": active_count,
            "executions_sampled": len(executions_frame),
            **usage_summary,
        }
        if executions_error:
            summary["executions_note"] = executions_error

        return ApiSnapshot(
            provider="n8n_cloud",
            status="pass",
            summary=summary,
            records={
                "workflows": workflows_frame,
                "executions": executions_frame,
            },
        )
    except Exception as exc:
        return ApiSnapshot("n8n_cloud", "fail", {}, {}, f"{exc.__class__.__name__}: {exc}")


def fetch_omnidimension_snapshot(settings: Settings) -> ApiSnapshot:
    if not settings.omnidimension_api_base_url or not settings.omnidimension_api_key:
        return ApiSnapshot(
            "omnidimension",
            "skipped",
            {},
            {},
            "OMNIDIMENSION_API_BASE_URL or OMNIDIMENSION_API_KEY missing",
        )

    headers = {"Authorization": f"Bearer {settings.omnidimension_api_key.get_secret_value()}"}
    base_url = str(settings.omnidimension_api_base_url).rstrip("/")
    endpoints = {
        "agents": "/agents",
        "phone_numbers": "/phone_number/list",
        "call_logs": "/calls/logs",
    }

    records: dict[str, pd.DataFrame] = {}
    summary: dict[str, Any] = {}
    errors: list[str] = []

    try:
        with httpx.Client(timeout=20, headers=headers) as client:
            for name, path in endpoints.items():
                response = client.get(
                    f"{base_url}{path}",
                    params={"pageno": "1", "pagesize": "100"},
                )
                if response.status_code != 200:
                    errors.append(f"{name}: HTTP {response.status_code}")
                    records[name] = pd.DataFrame()
                    continue
                payload = response.json()
                frame = _payload_frame(payload)
                records[name] = frame
                summary[f"{name}_sampled"] = len(frame)

        return ApiSnapshot(
            provider="omnidimension",
            status="partial" if errors else "pass",
            summary=summary,
            records=records,
            error="; ".join(errors) if errors else None,
        )
    except Exception as exc:
        return ApiSnapshot("omnidimension", "fail", {}, {}, f"{exc.__class__.__name__}: {exc}")


def fetch_gemini_billing_snapshot(settings: Settings, lookback_days: int = 90) -> ApiSnapshot:
    missing = []
    if not settings.google_billing_export_project_id:
        missing.append("GOOGLE_BILLING_EXPORT_PROJECT_ID")
    if not settings.google_billing_export_dataset:
        missing.append("GOOGLE_BILLING_EXPORT_DATASET")
    if (
        not settings.google_application_credentials
        and not settings.google_application_credentials_json
    ):
        missing.append("GOOGLE_APPLICATION_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS")
    if missing:
        return ApiSnapshot(
            "gemini",
            "skipped",
            {"missing": missing},
            {},
            f"Missing Gemini billing export settings: {', '.join(missing)}",
        )

    try:
        client = _bigquery_client(settings)
        table_name = settings.google_billing_export_table or _discover_billing_export_table(
            client,
            settings,
        )
    except Exception as exc:
        return ApiSnapshot("gemini", "fail", {}, {}, f"{exc.__class__.__name__}: {exc}")

    if not table_name:
        return ApiSnapshot(
            "gemini",
            "skipped",
            {
                "project_id": settings.google_billing_export_project_id,
                "dataset": settings.google_billing_export_dataset,
            },
            {},
            "No Google detailed billing export table was found in the configured dataset",
        )

    table_id = table_name.strip("`")
    if "." not in table_id:
        table_id = (
            f"{settings.google_billing_export_project_id}."
            f"{settings.google_billing_export_dataset}."
            f"{table_name}"
        )
    query = f"""
        WITH gemini_costs AS (
          SELECT
            DATE(usage_start_time) AS usage_date,
            project.id AS project_id,
            service.description AS service_description,
            sku.description AS sku_description,
            currency,
            SUM(usage.amount) AS usage_amount,
            usage.unit AS usage_unit,
            SUM(cost) AS gross_cost,
            SUM((
              SELECT COALESCE(SUM(credit.amount), 0)
              FROM UNNEST(credits) AS credit
            )) AS credits
          FROM `{table_id}`
          WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @lookback_days DAY)
            AND (
              LOWER(service.description) LIKE '%gemini%'
              OR LOWER(sku.description) LIKE '%gemini%'
              OR LOWER(sku.description) LIKE '%generative%'
              OR LOWER(sku.description) LIKE '%imagen%'
              OR LOWER(sku.description) LIKE '%veo%'
            )
          GROUP BY
            usage_date,
            project_id,
            service_description,
            sku_description,
            currency,
            usage_unit
        )
        SELECT
          usage_date,
          project_id,
          service_description,
          sku_description,
          currency,
          usage_amount,
          usage_unit,
          gross_cost,
          credits,
          gross_cost + credits AS net_cost
        FROM gemini_costs
        ORDER BY usage_date DESC, net_cost DESC
    """
    try:
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("lookback_days", "INT64", lookback_days)
            ]
        )
        rows = [dict(row.items()) for row in client.query(query, job_config=job_config).result()]
        frame = pd.DataFrame(rows)
        summary = _gemini_billing_summary(frame, settings)
        return ApiSnapshot(
            "gemini",
            "pass",
            {**summary, "export_table": table_name},
            {"billing_rows": frame},
        )
    except Exception as exc:
        return ApiSnapshot("gemini", "fail", {}, {}, f"{exc.__class__.__name__}: {exc}")


def higgsfield_snapshot(settings: Settings) -> ApiSnapshot:
    if (
        settings.higgsfield_api_base
        and (
            getattr(settings, "higgsfield_bearer_token", None)
            or getattr(settings, "higgsfield_cookie", None)
        )
    ):
        return _fetch_higgsfield_api_snapshot(settings)
    return _manual_higgsfield_snapshot(
        settings,
        "HIGGSFIELD_BEARER_TOKEN or HIGGSFIELD_COOKIE is not configured; "
        "showing manual fallback fields",
    )


def _higgsfield_api_base_url(settings: Settings) -> str:
    base_url = str(settings.higgsfield_api_base or "https://fnf.higgsfield.ai").rstrip("/")
    if base_url in {"https://dash.higgsfield.ai", "https://higgsfield.ai"}:
        return "https://fnf.higgsfield.ai"
    return base_url


def _fetch_higgsfield_api_snapshot(settings: Settings) -> ApiSnapshot:
    base_url = _higgsfield_api_base_url(settings)
    month_start = pd.Timestamp.today().replace(day=1).date().isoformat()
    today = date.today().isoformat()
    headers = _higgsfield_request_headers(settings)
    endpoints = {
        "statistics": (
            "/workspaces/credit-ledger/statistics",
            {"start_date": month_start, "end_date": today},
        ),
        "subscription": ("/workspaces/subscription", None),
        "subscription_features": ("/workspaces/subscription-features", {"version": "v2"}),
        "credit_ledger": (
            "/workspaces/credit-ledger",
            {"limit": "25", "page": "1", "start_date": month_start, "end_date": today},
        ),
        "invoices": ("/workspaces/invoices", {"limit": "25"}),
        "pending_invoices": ("/workspaces/pending-invoices", {"limit": "25"}),
        "payment_cards": ("/workspaces/payment-cards", {"limit": "25"}),
        "details": ("/workspaces/details", None),
        "job_costs": ("/job-sets/costs", None),
    }
    records: dict[str, pd.DataFrame] = {}
    payloads: dict[str, Any] = {}
    endpoint_statuses: list[dict[str, Any]] = []

    try:
        request_headers = {
            **headers,
            "Origin": "https://higgsfield.ai",
            "Referer": "https://higgsfield.ai/me/settings/usage",
        }
        with httpx.Client(timeout=20, headers=request_headers, follow_redirects=True) as client:
            for name, (path, params) in endpoints.items():
                response = client.get(f"{base_url}{path}", params=params)
                endpoint_statuses.append(
                    {
                        "endpoint": name,
                        "path": path,
                        "status_code": response.status_code,
                        "ok": response.status_code == 200,
                    }
                )
                if response.status_code != 200:
                    records[name] = pd.DataFrame()
                    continue
                payload = response.json()
                payloads[name] = payload
                records[name] = _payload_frame(payload)

        summary = _higgsfield_summary_from_payloads(payloads, settings)
        records["endpoint_statuses"] = pd.DataFrame(endpoint_statuses)
        unauthorized = [
            item for item in endpoint_statuses if item["status_code"] in {401, 403}
        ]
        all_unauthorized = len(unauthorized) == len(endpoint_statuses)
        if all_unauthorized:
            status = "fail"
        elif payloads.get("statistics"):
            status = "pass"
        else:
            status = "partial"
        errors = [
            f"{item['endpoint']}: HTTP {item['status_code']}"
            for item in endpoint_statuses
            if not item["ok"]
        ]
        error_message = "; ".join(errors) if status in {"partial", "fail"} and errors else None
        if all_unauthorized:
            error_message = (
                "Higgsfield token expired or missing cookie/session auth. "
                "Refresh HIGGSFIELD_BEARER_TOKEN or add HIGGSFIELD_COOKIE/"
                "HIGGSFIELD_EXTRA_HEADERS_JSON from a working browser request. "
                f"{error_message}"
            )
        return ApiSnapshot(
            "higgsfield_ai",
            status,
            summary,
            records,
            error_message,
        )
    except Exception as exc:
        manual = _manual_higgsfield_snapshot(settings, None)
        return ApiSnapshot(
            "higgsfield_ai",
            "fail",
            manual.summary,
            manual.records,
            f"{exc.__class__.__name__}: {exc}",
        )


def _higgsfield_request_headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Origin": "https://higgsfield.ai",
        "Referer": "https://higgsfield.ai/me/settings/usage",
    }
    bearer_token = getattr(settings, "higgsfield_bearer_token", None)
    cookie = getattr(settings, "higgsfield_cookie", None)

    if bearer_token:
        token = bearer_token.get_secret_value().strip()
        if token.lower().startswith("bearer "):
            headers["Authorization"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"
    if cookie:
        headers["Cookie"] = cookie.get_secret_value().strip()
    headers.update(_higgsfield_extra_headers(settings))
    return headers


def _higgsfield_extra_headers(settings: Settings) -> dict[str, str]:
    extra_headers_json = getattr(settings, "higgsfield_extra_headers_json", None)
    if not extra_headers_json:
        return {}
    raw_headers = extra_headers_json.get_secret_value()
    try:
        parsed = json.loads(raw_headers)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}

    blocked_headers = {"host", "content-length", "connection", "accept-encoding"}
    headers = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or value in (None, ""):
            continue
        if key.lower() in blocked_headers:
            continue
        headers[key] = str(value)
    return headers


def _manual_higgsfield_snapshot(settings: Settings, error: str | None = None) -> ApiSnapshot:
    rows = [
        {
            "metric": "current_balance",
            "value": settings.higgsfield_current_balance,
            "unit": settings.higgsfield_balance_unit,
            "source": "manual_secret",
        },
        {
            "metric": "usage_this_month",
            "value": settings.higgsfield_usage_this_month,
            "unit": settings.higgsfield_balance_unit,
            "source": "manual_secret",
        },
        {
            "metric": "monthly_usage_limit",
            "value": settings.higgsfield_monthly_usage_limit,
            "unit": settings.higgsfield_balance_unit,
            "source": "manual_secret",
        },
        {
            "metric": "monthly_cost",
            "value": settings.higgsfield_monthly_cost,
            "unit": settings.higgsfield_currency_code,
            "source": "manual_secret",
        },
    ]
    frame = pd.DataFrame(rows)
    configured = any(row["value"] not in (None, "") for row in rows)
    summary = {
        "plan_name": settings.higgsfield_plan_name,
        "current_balance": settings.higgsfield_current_balance,
        "balance_unit": settings.higgsfield_balance_unit,
        "usage_this_month": settings.higgsfield_usage_this_month,
        "monthly_usage_limit": settings.higgsfield_monthly_usage_limit,
        "monthly_cost": settings.higgsfield_monthly_cost,
        "currency_code": settings.higgsfield_currency_code,
        "renewal_date": settings.higgsfield_renewal_date,
        "usage_dashboard_url": settings.higgsfield_usage_dashboard_url,
        "billing_dashboard_url": settings.higgsfield_billing_dashboard_url,
    }
    return ApiSnapshot(
        "higgsfield_ai",
        "manual" if configured else "skipped",
        summary,
        {"manual_metrics": frame},
        error
        if error
        else None
        if configured
        else "Higgsfield manual cost/balance settings are not configured",
    )


def _payload_frame(payload: Any) -> pd.DataFrame:
    records = _payload_records(payload)
    if records:
        return pd.DataFrame(records)
    if isinstance(payload, dict):
        return pd.DataFrame([_flatten_mapping(payload)])
    return pd.DataFrame([{"value": payload}])


def _higgsfield_summary_from_payloads(
    payloads: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    merged = {
        key: value
        for payload in payloads.values()
        for key, value in _flatten_mapping(payload).items()
    }
    usage_payload = payloads.get("statistics") or payloads.get("usage_stats") or {}
    usage_flat = _flatten_mapping(usage_payload)

    current_balance = _first_mapping_value(
        merged,
        [
            "current_balance",
            "credit_balance",
            "credits_balance",
            "remaining_credits",
            "balance",
            "available_credits",
        ],
    )
    usage_this_month = _first_mapping_value(
        usage_flat,
        [
            "credits_used",
            "credit_used",
            "used_credits",
            "total_credits",
            "usage",
            "total_usage",
            "credits_spent",
        ],
    )
    monthly_usage_limit = _first_mapping_value(
        merged,
        [
            "monthly_usage_limit",
            "credit_limit",
            "credits_limit",
            "monthly_credits",
            "limit",
            "quota",
        ],
    )
    monthly_cost = _first_mapping_value(
        merged,
        [
            "monthly_cost",
            "amount",
            "price",
            "subscription_amount",
            "plan_amount",
            "unit_amount",
        ],
    )
    return {
        "plan_name": _first_mapping_value(
            merged,
            ["plan_name", "plan", "subscription_plan", "product_name", "name"],
        )
        or settings.higgsfield_plan_name,
        "current_balance": current_balance or settings.higgsfield_current_balance,
        "balance_unit": settings.higgsfield_balance_unit,
        "usage_this_month": usage_this_month or settings.higgsfield_usage_this_month,
        "monthly_usage_limit": monthly_usage_limit or settings.higgsfield_monthly_usage_limit,
        "monthly_cost": monthly_cost or settings.higgsfield_monthly_cost,
        "currency_code": _first_mapping_value(merged, ["currency", "currency_code"])
        or settings.higgsfield_currency_code,
        "renewal_date": _first_mapping_value(
            merged,
            ["renewal_date", "current_period_end", "next_billing_date", "period_end"],
        )
        or settings.higgsfield_renewal_date,
        "usage_dashboard_url": settings.higgsfield_usage_dashboard_url,
        "billing_dashboard_url": settings.higgsfield_billing_dashboard_url,
        "api_payloads_loaded": len(payloads),
    }


def _flatten_mapping(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flattened = {}
        for key, item in value.items():
            child_key = f"{prefix}_{key}" if prefix else str(key)
            flattened.update(_flatten_mapping(item, child_key))
        return flattened
    if isinstance(value, list):
        return {prefix: json.dumps(value, default=str)} if prefix else {}
    return {prefix: value} if prefix else {}


def _first_mapping_value(mapping: dict[str, Any], candidates: list[str]) -> Any:
    normalized = {key.lower(): value for key, value in mapping.items()}
    for candidate in candidates:
        candidate_lower = candidate.lower()
        for key, value in normalized.items():
            if key.endswith(candidate_lower) and value not in (None, ""):
                return value
    return None


def monthly_totals_by_currency(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["currency_code", "monthly_equivalent"])
    return (
        frame.groupby("currency_code", dropna=False)["monthly_equivalent"]
        .sum()
        .reset_index()
        .sort_values("currency_code")
    )


def n8n_execution_limit(settings: Settings) -> int | None:
    if settings.n8n_execution_limit:
        return settings.n8n_execution_limit
    markers = load_manual_registry()["manual_usage_markers"]
    for marker in markers:
        if (
            marker.get("provider") == "n8n_cloud"
            and marker.get("metric_name") == "monthly_execution_limit"
        ):
            try:
                return int(marker["value"])
            except (TypeError, ValueError):
                return None
    return None


def streamlit_safe_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert nested/mixed object columns into strings so PyArrow can render them."""
    if frame.empty:
        return frame

    display = frame.copy()
    for column in display.columns:
        if display[column].dtype == "object":
            display[column] = display[column].map(_streamlit_safe_object_value)
    return display


def _bigquery_client(settings: Settings) -> bigquery.Client:
    if settings.google_application_credentials_json:
        info = json.loads(settings.google_application_credentials_json.get_secret_value())
        credentials = service_account.Credentials.from_service_account_info(info)
        return bigquery.Client(
            project=settings.google_billing_export_project_id,
            credentials=credentials,
        )
    return bigquery.Client(
        project=settings.google_billing_export_project_id,
        credentials=service_account.Credentials.from_service_account_file(
            settings.google_application_credentials
        ),
    )


def _discover_billing_export_table(
    client: bigquery.Client,
    settings: Settings,
) -> str | None:
    dataset_ref = (
        f"{settings.google_billing_export_project_id}."
        f"{settings.google_billing_export_dataset}"
    )
    tables = list(client.list_tables(dataset_ref))
    table_ids = [table.table_id for table in tables]
    for prefix in ("gcp_billing_export_resource_v1_", "gcp_billing_export_v1_"):
        matches = sorted(table_id for table_id in table_ids if table_id.startswith(prefix))
        if matches:
            return matches[0]
    return None


def _gemini_billing_summary(frame: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    if frame.empty:
        return {
            "rows": 0,
            "current_month_cost": 0,
            "currency": settings.default_currency,
            "project_spend_cap_usd": settings.google_ai_studio_project_spend_cap_usd,
            "monthly_usage_limit_usd": settings.google_ai_studio_monthly_usage_limit_usd,
        }
    costs = pd.to_numeric(frame["net_cost"], errors="coerce").fillna(0)
    dates = pd.to_datetime(frame["usage_date"], errors="coerce")
    month_start = pd.Timestamp.today().replace(day=1).date()
    current_month = frame[dates.dt.date >= month_start]
    current_month_cost = pd.to_numeric(current_month["net_cost"], errors="coerce").fillna(0).sum()
    currency = (
        frame["currency"].dropna().iloc[0]
        if "currency" in frame and not frame.empty
        else None
    )
    return {
        "rows": len(frame),
        "total_cost": float(costs.sum()),
        "current_month_cost": float(current_month_cost),
        "currency": currency or settings.default_currency,
        "project_spend_cap_usd": settings.google_ai_studio_project_spend_cap_usd,
        "monthly_usage_limit_usd": settings.google_ai_studio_monthly_usage_limit_usd,
        "latest_usage_date": dates.max().date().isoformat() if not dates.dropna().empty else None,
    }


def _payload_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in (
        "data",
        "items",
        "results",
        "records",
        "logs",
        "agents",
        "bots",
        "phone_numbers",
        "call_log_data",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [payload]


def _fetch_n8n_current_month_usage(
    client: httpx.Client,
    base_url: str,
    settings: Settings,
) -> dict[str, Any]:
    month_start = pd.Timestamp.now(tz="Asia/Kolkata").replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    cursor = None
    used = 0
    pages = 0
    oldest_seen: pd.Timestamp | None = None

    while pages < N8N_EXECUTION_MAX_PAGES:
        params = {"limit": str(N8N_EXECUTION_PAGE_LIMIT)}
        if cursor:
            params["cursor"] = cursor
        response = client.get(f"{base_url}/api/v1/executions", params=params)
        if response.status_code != 200:
            return {
                "execution_usage_status": f"failed_http_{response.status_code}",
                "execution_limit": n8n_execution_limit(settings),
                "executions_used_current_month": None,
                "executions_remaining_current_month": None,
            }

        payload = response.json()
        records = _payload_records(payload)
        if not records:
            break

        stop_after_page = False
        for record in records:
            started_at = _parse_timestamp(record.get("startedAt"))
            if started_at is None:
                continue
            oldest_seen = started_at if oldest_seen is None else min(oldest_seen, started_at)
            if started_at >= month_start:
                used += 1
            else:
                stop_after_page = True

        pages += 1
        cursor = payload.get("nextCursor") if isinstance(payload, dict) else None
        if stop_after_page or not cursor:
            break

    limit = n8n_execution_limit(settings)
    remaining = limit - used if limit is not None else None
    return {
        "execution_usage_status": "estimated_from_executions_api",
        "execution_limit": limit,
        "executions_used_current_month": used,
        "executions_remaining_current_month": remaining,
        "execution_usage_pages_scanned": pages,
        "execution_usage_oldest_seen": oldest_seen.isoformat() if oldest_seen else None,
    }


def _streamlit_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, dict | list | tuple | set):
        return json.dumps(value, default=str, sort_keys=True)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int | float):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _streamlit_safe_object_value(value: Any) -> str | None:
    safe_value = _streamlit_safe_value(value)
    if safe_value is None:
        return None
    return str(safe_value)


def _parse_timestamp(value: Any) -> pd.Timestamp | None:
    if not value:
        return None
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return None
    return timestamp.tz_convert("Asia/Kolkata")


def _project_ref_from_supabase_url(value: str) -> str | None:
    host = value.replace("https://", "").replace("http://", "").split("/")[0]
    if host.endswith(".supabase.co"):
        return host.split(".")[0]
    return None


def _project_ref_from_pooler_user(value: str) -> str | None:
    if value.startswith("postgres."):
        return value.split(".", 1)[1]
    return None


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _monthly_equivalent(row: pd.Series) -> Decimal | None:
    amount = row.get("amount")
    if amount is None:
        return None
    cycle = str(row.get("billing_cycle") or "").lower()
    if cycle == "annual":
        return amount / Decimal("12")
    return amount


def _amount_to_inr(row: pd.Series) -> Decimal | None:
    amount = row.get("monthly_amount")
    fx_rate = row.get("fx_rate_to_inr")
    if amount is None or fx_rate is None:
        return None
    try:
        if pd.isna(amount) or pd.isna(fx_rate):
            return None
    except (TypeError, ValueError):
        pass
    return amount * fx_rate


def _days_until(value: date | None) -> int | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        value = value.date()
    return (value - date.today()).days
