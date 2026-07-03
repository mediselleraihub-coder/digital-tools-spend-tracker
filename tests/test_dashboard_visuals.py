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
