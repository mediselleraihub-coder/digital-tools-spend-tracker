from __future__ import annotations

from decimal import Decimal

import pandas as pd

from spend_tracker.config import Settings
from spend_tracker.dashboard.app import (
    _currency_exposure,
    _group_sum,
    _quota_gauge,
    _renewal_month_exposure,
)
from spend_tracker.dashboard.data import (
    _bearer_header_value,
    _higgsfield_clerk_refresh_configured,
    _higgsfield_request_headers,
    _higgsfield_summary_from_payloads,
    combined_commitments_dataframe,
    higgsfield_snapshot,
    manual_assets_dataframe,
    manual_subscriptions_dataframe,
    planning_fx_dataframe,
    streamlit_safe_dataframe,
)


def make_settings(**overrides: object) -> Settings:
    values = {
        "SUPABASE_URL": "https://vpkkiehwmhkmmptetpfl.supabase.co",
        "SUPABASE_DB_PASSWORD": "password",
        "SUPABASE_DB_HOST": "aws-1-ap-northeast-1.pooler.supabase.com",
        "SUPABASE_DB_USER": "postgres.vpkkiehwmhkmmptetpfl",
    }
    values.update(overrides)
    return Settings(**values)


def test_commitments_include_inr_monthly_values() -> None:
    subscriptions = manual_subscriptions_dataframe(make_settings())
    assets = manual_assets_dataframe()
    fx_rates = planning_fx_dataframe()

    commitments = combined_commitments_dataframe(subscriptions, assets, fx_rates)

    assert not commitments.empty
    assert "monthly_inr" in commitments.columns
    assert commitments["monthly_inr"].map(lambda value: value is None or value >= 0).all()
    assert commitments.loc[
        commitments["provider"] == "godaddy_titan_email", "monthly_inr"
    ].notna().any()


def test_streamlit_safe_dataframe_serializes_nested_columns() -> None:
    frame = pd.DataFrame(
        {
            "id": [1, 2],
            "nodes": [[{"id": 1}], "gid=0"],
            "amount": [Decimal("10.50"), None],
        }
    )

    safe = streamlit_safe_dataframe(frame)

    assert safe.loc[0, "nodes"] == '[{"id": 1}]'
    assert safe.loc[1, "nodes"] == "gid=0"
    assert safe.loc[0, "amount"] == "10.50"


def test_dashboard_chart_frames_are_buildable() -> None:
    subscriptions = manual_subscriptions_dataframe(make_settings())
    assets = manual_assets_dataframe()
    commitments = combined_commitments_dataframe(
        subscriptions,
        assets,
        planning_fx_dataframe(),
    )

    assert not _group_sum(commitments, "category", "monthly_inr").empty
    assert not _renewal_month_exposure(commitments).empty
    assert not _currency_exposure(commitments).empty

    gauge = _quota_gauge(used=6, limit=2500)
    assert gauge.data


def test_higgsfield_snapshot_uses_manual_settings() -> None:
    snapshot = higgsfield_snapshot(
        make_settings(
            HIGGSFIELD_PLAN_NAME="Pro",
            HIGGSFIELD_MONTHLY_COST="29",
            HIGGSFIELD_CURRENT_BALANCE="120",
            HIGGSFIELD_USAGE_THIS_MONTH="30",
            HIGGSFIELD_MONTHLY_USAGE_LIMIT="200",
        )
    )

    assert snapshot.status == "manual"
    assert snapshot.summary["plan_name"] == "Pro"
    assert snapshot.summary["current_balance"] == "120"
    assert not snapshot.records["manual_metrics"].empty


def test_higgsfield_summary_extracts_nested_api_fields() -> None:
    summary = _higgsfield_summary_from_payloads(
        {
            "usage_stats": {"data": {"credits_used": 42}},
            "subscription": {
                "subscription": {
                    "plan_name": "Creator",
                    "current_period_end": "2026-07-31",
                    "currency": "USD",
                    "amount": 19,
                }
            },
            "credits": {"credits": {"remaining_credits": 108, "credit_limit": 150}},
        },
        make_settings(),
    )

    assert summary["plan_name"] == "Creator"
    assert summary["usage_this_month"] == 42
    assert summary["current_balance"] == 108
    assert summary["monthly_usage_limit"] == 150


def test_higgsfield_summary_preserves_zero_usage_and_credit_seat_limit() -> None:
    summary = _higgsfield_summary_from_payloads(
        {
            "statistics": {"total_credits_spent": 0, "jobs_created": 0, "currency": "usd"},
            "subscription": {
                "plan_name": "ultra",
                "credits_per_seat": 3000,
                "current_period_end": "2026-07-22T12:18:16Z",
            },
        },
        make_settings(),
    )

    assert summary["usage_this_month"] == 0
    assert summary["monthly_usage_limit"] == 3000
    assert summary["current_balance"] == Decimal("3000")


def test_higgsfield_request_headers_support_cookie_and_extra_headers() -> None:
    headers = _higgsfield_request_headers(
        make_settings(
            HIGGSFIELD_BEARER_TOKEN="Bearer clerk-token",
            HIGGSFIELD_COOKIE="__session=session-token",
            HIGGSFIELD_EXTRA_HEADERS_JSON='{"x-client": "web", "host": "blocked"}',
        )
    )

    assert headers["Authorization"] == "Bearer clerk-token"
    assert headers["Cookie"] == "__session=session-token"
    assert headers["x-client"] == "web"
    assert "host" not in {key.lower() for key in headers}


def test_higgsfield_request_headers_prefer_refreshed_token() -> None:
    headers = _higgsfield_request_headers(
        make_settings(HIGGSFIELD_BEARER_TOKEN="expired-token"),
        refreshed_token="fresh-token",
    )

    assert headers["Authorization"] == "Bearer fresh-token"


def test_higgsfield_clerk_refresh_requires_all_secret_inputs() -> None:
    partial = make_settings(
        HIGGSFIELD_CLERK_TOKEN_URL="https://clerk.higgsfield.ai/v1/client/sessions/x/tokens",
        HIGGSFIELD_CLERK_COOKIE="__client=value",
    )
    complete = make_settings(
        HIGGSFIELD_CLERK_TOKEN_URL="https://clerk.higgsfield.ai/v1/client/sessions/x/tokens",
        HIGGSFIELD_CLERK_COOKIE="__client=value",
        HIGGSFIELD_CLERK_FORM_TOKEN="client-token",
    )

    assert not _higgsfield_clerk_refresh_configured(partial)
    assert _higgsfield_clerk_refresh_configured(complete)


def test_bearer_header_value_preserves_existing_prefix() -> None:
    assert _bearer_header_value("Bearer token") == "Bearer token"
    assert _bearer_header_value("token") == "Bearer token"


def test_higgsfield_request_headers_tolerate_older_settings_shape() -> None:
    class OlderSettings:
        higgsfield_bearer_token = None

    headers = _higgsfield_request_headers(OlderSettings())  # type: ignore[arg-type]

    assert headers["Accept"] == "application/json"
    assert "Cookie" not in headers
