from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from spend_tracker.config import load_settings
from spend_tracker.dashboard import data as dashboard_data
from spend_tracker.dashboard.data import (
    check_supabase_persistence,
    combined_commitments_dataframe,
    fetch_n8n_snapshot,
    fetch_omnidimension_snapshot,
    manual_assets_dataframe,
    manual_subscriptions_dataframe,
    planning_fx_dataframe,
    provider_status_dataframe,
    streamlit_safe_dataframe,
    usage_markers_dataframe,
)

CHART_CONFIG = {"displayModeBar": False, "responsive": True}
COLOR_SEQUENCE = ["#2563eb", "#059669", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2"]


st.set_page_config(
    page_title="Digital Tools Spend Tracker",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=300, show_spinner=False)
def cached_manual_subscriptions() -> pd.DataFrame:
    return manual_subscriptions_dataframe(load_settings())


@st.cache_data(ttl=300, show_spinner=False)
def cached_manual_assets() -> pd.DataFrame:
    return manual_assets_dataframe()


@st.cache_data(ttl=300, show_spinner=False)
def cached_usage_markers() -> pd.DataFrame:
    return usage_markers_dataframe()


@st.cache_data(ttl=300, show_spinner=False)
def cached_fx_rates() -> pd.DataFrame:
    return planning_fx_dataframe()


@st.cache_data(ttl=180, show_spinner=False)
def cached_n8n() -> dict[str, Any]:
    snapshot = fetch_n8n_snapshot(load_settings())
    return {
        "provider": snapshot.provider,
        "status": snapshot.status,
        "summary": snapshot.summary,
        "records": snapshot.records,
        "error": snapshot.error,
    }


@st.cache_data(ttl=180, show_spinner=False)
def cached_omnidimension() -> dict[str, Any]:
    snapshot = fetch_omnidimension_snapshot(load_settings())
    return {
        "provider": snapshot.provider,
        "status": snapshot.status,
        "summary": snapshot.summary,
        "records": snapshot.records,
        "error": snapshot.error,
    }


@st.cache_data(ttl=600, show_spinner=False)
def cached_gemini_billing() -> dict[str, Any]:
    fetcher = getattr(dashboard_data, "fetch_gemini_billing_snapshot", None)
    if fetcher is None:
        return _missing_provider_snapshot(
            "gemini",
            "Gemini billing fetcher is not available in the deployed data module yet.",
        )
    snapshot = fetcher(load_settings())
    return {
        "provider": snapshot.provider,
        "status": snapshot.status,
        "summary": snapshot.summary,
        "records": snapshot.records,
        "error": snapshot.error,
    }


@st.cache_data(ttl=300, show_spinner=False)
def cached_higgsfield() -> dict[str, Any]:
    fetcher = getattr(dashboard_data, "higgsfield_snapshot", None)
    if fetcher is None:
        return _missing_provider_snapshot(
            "higgsfield_ai",
            "Higgsfield fetcher is not available in the deployed data module yet.",
        )
    snapshot = fetcher(load_settings())
    return {
        "provider": snapshot.provider,
        "status": snapshot.status,
        "summary": snapshot.summary,
        "records": snapshot.records,
        "error": snapshot.error,
    }


def _missing_provider_snapshot(provider: str, message: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "status": "skipped",
        "summary": {},
        "records": {},
        "error": message,
    }


@st.cache_data(ttl=180, show_spinner=False)
def cached_persistence_status() -> dict[str, Any]:
    status = check_supabase_persistence(load_settings())
    return {
        "status": status.status,
        "message": status.message,
        "detail": status.detail,
    }


def main() -> None:
    settings = load_settings()
    persistence_status = cached_persistence_status()

    st.title("Digital Tools Spend Tracker")
    st.caption(
        "Operational visibility for renewals, live provider usage, subscriptions, "
        "and provider readiness."
    )

    manual_subscriptions = cached_manual_subscriptions()
    manual_assets = cached_manual_assets()
    usage_markers = cached_usage_markers()
    fx_rates = cached_fx_rates()
    commitments = combined_commitments_dataframe(manual_subscriptions, manual_assets, fx_rates)
    n8n_snapshot = cached_n8n()
    omni_snapshot = cached_omnidimension()
    gemini_snapshot = cached_gemini_billing()
    higgsfield = cached_higgsfield()

    with st.sidebar:
        st.header("Controls")
        refresh = st.button("Refresh live data", use_container_width=True)
        if refresh:
            st.cache_data.clear()
            st.rerun()
        st.divider()
        st.write("Default currency:", settings.default_currency)
        st.write("Timezone:", settings.timezone)
        render_persistence_sidebar(persistence_status)
        st.divider()
        st.caption("INR visuals use planning FX until Supabase FX rates are populated.")

    tabs = st.tabs(
        [
            "Overview",
            "Renewals",
            "n8n",
            "OmniDimension",
            "Titan / Email",
            "Gemini",
            "Higgsfield",
            "Source Health",
        ]
    )

    with tabs[0]:
        render_overview(commitments, fx_rates, n8n_snapshot, omni_snapshot)
    with tabs[1]:
        render_renewals(commitments)
    with tabs[2]:
        render_n8n(n8n_snapshot)
    with tabs[3]:
        render_omnidimension(omni_snapshot, usage_markers, commitments)
    with tabs[4]:
        render_titan_email(commitments, manual_assets)
    with tabs[5]:
        render_gemini(settings, gemini_snapshot)
    with tabs[6]:
        render_higgsfield(higgsfield)
    with tabs[7]:
        render_health(
            settings,
            n8n_snapshot,
            omni_snapshot,
            gemini_snapshot,
            higgsfield,
            persistence_status,
            fx_rates,
        )


def render_overview(
    commitments: pd.DataFrame,
    fx_rates: pd.DataFrame,
    n8n_snapshot: dict[str, Any],
    omni_snapshot: dict[str, Any],
) -> None:
    monthly_inr = _decimal_sum(commitments.get("monthly_inr"))
    annualized_inr = monthly_inr * 12
    renewals_due_45 = _count_due_soon(commitments, days=45)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Monthly run-rate INR", _inr(monthly_inr))
    col2.metric("Annualized run-rate INR", _inr(annualized_inr))
    col3.metric("Renewals in 45 days", renewals_due_45)
    col4.metric("Live API sources", _live_source_count(n8n_snapshot, omni_snapshot))

    if commitments.empty:
        st.info("No subscription or asset commitments are configured yet.")
        return

    category_chart, vendor_chart = st.columns(2)
    with category_chart:
        st.subheader("INR monthly run-rate by category")
        category_frame = _group_sum(commitments, "category", "monthly_inr")
        fig = px.bar(
            category_frame,
            x="monthly_inr",
            y="category",
            orientation="h",
            color="category",
            color_discrete_sequence=COLOR_SEQUENCE,
            labels={"monthly_inr": "Monthly INR", "category": "Category"},
            text="monthly_inr",
        )
        _style_bar(fig)
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with vendor_chart:
        st.subheader("INR monthly run-rate by provider")
        vendor_frame = _group_sum(commitments, "provider", "monthly_inr")
        fig = px.bar(
            vendor_frame,
            x="provider",
            y="monthly_inr",
            color="provider",
            color_discrete_sequence=COLOR_SEQUENCE,
            labels={"monthly_inr": "Monthly INR", "provider": "Provider"},
            text="monthly_inr",
        )
        _style_bar(fig)
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    left, right = st.columns(2)
    with left:
        st.subheader("Tool portfolio map")
        treemap = commitments[commitments["monthly_inr"].notna()].copy()
        if treemap.empty:
            st.info("No INR-normalized commitments to map.")
        else:
            fig = px.treemap(
                treemap,
                path=["category", "provider", "name"],
                values="monthly_inr",
                color="category",
                color_discrete_sequence=COLOR_SEQUENCE,
                hover_data=["currency_code", "monthly_amount", "renewal_date"],
            )
            fig.update_layout(margin=dict(l=0, r=0, t=8, b=0))
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with right:
        st.subheader("Renewal exposure by month")
        renewal_frame = _renewal_month_exposure(commitments)
        if renewal_frame.empty:
            st.info("No renewal dates configured.")
        else:
            fig = px.bar(
                renewal_frame,
                x="renewal_month",
                y="monthly_inr",
                color="category",
                color_discrete_sequence=COLOR_SEQUENCE,
                labels={"monthly_inr": "Monthly INR exposure", "renewal_month": "Month"},
                text="monthly_inr",
            )
            _style_bar(fig, texttemplate="%{y:,.0f}")
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.subheader("Original currency exposure")
    currency_frame = _currency_exposure(commitments)
    st.dataframe(_display_frame(currency_frame), use_container_width=True, hide_index=True)

    with st.expander("Planning FX rates used for INR visuals"):
        st.dataframe(_display_frame(fx_rates), use_container_width=True, hide_index=True)


def render_renewals(commitments: pd.DataFrame) -> None:
    st.subheader("Renewal command center")
    renewals = commitments[commitments["renewal_date"].notna()].copy()
    if renewals.empty:
        st.info("No renewal dates configured.")
        return

    due_30 = _count_due_soon(renewals, 30)
    due_60 = _count_due_soon(renewals, 60)
    due_90 = _count_due_soon(renewals, 90)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Due in 30 days", due_30)
    col2.metric("Due in 60 days", due_60)
    col3.metric("Due in 90 days", due_90)
    col4.metric("Tracked renewals", len(renewals))

    left, right = st.columns(2)
    with left:
        st.subheader("Renewal Gantt")
        timeline = renewals.copy()
        timeline["start_date"] = pd.Timestamp.today().date()
        timeline["display_name"] = timeline["provider"] + " - " + timeline["name"]
        fig = px.timeline(
            timeline,
            x_start="start_date",
            x_end="renewal_date",
            y="display_name",
            color="category",
            color_discrete_sequence=COLOR_SEQUENCE,
            hover_data=["monthly_inr", "currency_code", "days_to_renewal"],
        )
        fig.update_yaxes(autorange="reversed")
        _style_timeline(fig)
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with right:
        st.subheader("Renewal urgency")
        urgency = renewals.copy()
        urgency["urgency"] = urgency["days_to_renewal"].map(_urgency_bucket)
        urgency_frame = (
            urgency.groupby("urgency", dropna=False).size().reset_index(name="renewal_count")
        )
        fig = px.bar(
            urgency_frame,
            x="urgency",
            y="renewal_count",
            color="urgency",
            color_discrete_sequence=COLOR_SEQUENCE,
            labels={"urgency": "Window", "renewal_count": "Renewals"},
            text="renewal_count",
        )
        _style_bar(fig)
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    left, right = st.columns(2)
    with left:
        st.subheader("Renewal calendar density")
        calendar_frame = _calendar_density(renewals)
        if calendar_frame.empty:
            st.info("No renewal density data.")
        else:
            fig = px.density_heatmap(
                calendar_frame,
                x="day",
                y="month",
                z="renewal_count",
                color_continuous_scale="Blues",
                labels={"day": "Day", "month": "Month", "renewal_count": "Renewals"},
            )
            fig.update_layout(margin=dict(l=0, r=0, t=8, b=0), height=360)
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with right:
        st.subheader("Auto-renew risk")
        auto_frame = renewals.copy()
        auto_frame["auto_renew_status"] = auto_frame["auto_renew"].map(_auto_renew_label)
        grouped = auto_frame.groupby("auto_renew_status").size().reset_index(name="count")
        fig = px.pie(
            grouped,
            names="auto_renew_status",
            values="count",
            hole=0.52,
            color_discrete_sequence=COLOR_SEQUENCE,
        )
        fig.update_layout(margin=dict(l=0, r=0, t=8, b=0), height=360)
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.subheader("Renewal checklist")
    st.dataframe(
        _display_frame(
            renewals[
                [
                    "record_type",
                    "provider",
                    "category",
                    "name",
                    "renewal_date",
                    "days_to_renewal",
                    "monthly_inr",
                    "currency_code",
                    "auto_renew",
                    "status",
                ]
            ].sort_values("renewal_date")
        ),
        use_container_width=True,
        hide_index=True,
    )


def render_n8n(snapshot: dict[str, Any]) -> None:
    render_snapshot_banner(snapshot)
    summary = snapshot.get("summary") or {}
    records = snapshot.get("records") or {}
    workflows = records.get("workflows", pd.DataFrame())
    executions = _prepare_n8n_executions(records.get("executions", pd.DataFrame()), workflows)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Workflows sampled", summary.get("workflows_sampled", 0))
    col2.metric("Active workflows", summary.get("active_workflows_sampled", 0))
    col3.metric(
        "Executions this month",
        _metric_value(summary.get("executions_used_current_month")),
    )
    col4.metric("Execution limit", _metric_value(summary.get("execution_limit")))
    col5.metric("Remaining", _metric_value(summary.get("executions_remaining_current_month")))

    gauge_col, mix_col = st.columns(2)
    with gauge_col:
        st.subheader("Execution quota utilization")
        fig = _quota_gauge(
            used=summary.get("executions_used_current_month"),
            limit=summary.get("execution_limit"),
        )
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with mix_col:
        st.subheader("Execution status mix")
        if executions.empty or "status" not in executions:
            st.info("No execution status data returned.")
        else:
            status_frame = executions.groupby("status").size().reset_index(name="count")
            fig = px.pie(
                status_frame,
                names="status",
                values="count",
                hole=0.48,
                color_discrete_sequence=COLOR_SEQUENCE,
            )
            fig.update_layout(margin=dict(l=0, r=0, t=8, b=0), height=360)
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    left, right = st.columns(2)
    with left:
        st.subheader("Daily executions")
        daily = _daily_count(executions, "started_at_local", "executions")
        if daily.empty:
            st.info("No dated execution rows returned.")
        else:
            fig = px.area(
                daily,
                x="date",
                y="executions",
                markers=True,
                color_discrete_sequence=["#2563eb"],
            )
            _style_line(fig)
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with right:
        st.subheader("Executions by workflow")
        if executions.empty or "workflow_name" not in executions:
            st.info("No workflow execution data returned.")
        else:
            workflow_counts = (
                executions.groupby("workflow_name").size().reset_index(name="executions")
            )
            fig = px.bar(
                workflow_counts.sort_values("executions", ascending=True).tail(12),
                x="executions",
                y="workflow_name",
                orientation="h",
                color="workflow_name",
                color_discrete_sequence=COLOR_SEQUENCE,
            )
            _style_bar(fig)
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.subheader("Failed executions by workflow")
    failed = pd.DataFrame()
    if not executions.empty and "status" in executions:
        failed = executions[executions["status"].astype(str) == "error"]
    if failed.empty:
        st.success("No failed executions in the sampled execution rows.")
    else:
        failed_counts = failed.groupby("workflow_name").size().reset_index(name="failures")
        fig = px.bar(
            failed_counts.sort_values("failures", ascending=True),
            x="failures",
            y="workflow_name",
            orientation="h",
            color="workflow_name",
            color_discrete_sequence=COLOR_SEQUENCE,
            text="failures",
        )
        _style_bar(fig, texttemplate="%{x:,.0f}")
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with st.expander("Execution usage details"):
        usage_frame = pd.DataFrame(
            [
                {"metric": key, "value": value}
                for key, value in summary.items()
                if key.startswith("execution") or key.startswith("executions")
            ]
        )
        st.dataframe(_display_frame(usage_frame), use_container_width=True, hide_index=True)

    render_dataframe_section("Workflows", workflows)
    render_dataframe_section("Executions", executions)


def render_omnidimension(
    snapshot: dict[str, Any],
    usage_markers: pd.DataFrame,
    commitments: pd.DataFrame,
) -> None:
    render_snapshot_banner(snapshot)
    summary = snapshot.get("summary") or {}
    records = snapshot.get("records") or {}
    calls = _prepare_generic_dated_records(records.get("call_logs", pd.DataFrame()))
    phone_renewals = commitments[commitments["provider"] == "omnidimension"].copy()

    markers = _markers_dict(usage_markers, "omnidimension")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Agents sampled", summary.get("agents_sampled", 0))
    col2.metric("Phone numbers", summary.get("phone_numbers_sampled", 0))
    col3.metric("Wallet balance", _metric_with_unit(markers.get("wallet_balance"), "USD"))
    col4.metric("Minutes left", _metric_value(markers.get("minutes_left")))

    left, right = st.columns(2)
    with left:
        st.subheader("Call volume by day")
        daily = _daily_count(calls, "event_time", "calls")
        if daily.empty:
            st.info("No dated call log rows returned.")
        else:
            fig = px.bar(daily, x="date", y="calls", color_discrete_sequence=["#059669"])
            _style_bar(fig)
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with right:
        st.subheader("Phone number renewal timeline")
        if phone_renewals.empty:
            st.info("No OmniDimension phone renewals configured.")
        else:
            timeline = phone_renewals.copy()
            timeline["start_date"] = pd.Timestamp.today().date()
            fig = px.timeline(
                timeline,
                x_start="start_date",
                x_end="renewal_date",
                y="name",
                color="currency_code",
                hover_data=["monthly_amount", "monthly_inr", "days_to_renewal"],
                color_discrete_sequence=COLOR_SEQUENCE,
            )
            fig.update_yaxes(autorange="reversed")
            _style_timeline(fig)
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    left, right = st.columns(2)
    with left:
        st.subheader("Calls by status")
        status_col = _first_existing_column(calls, ["status", "call_status", "outcome"])
        if calls.empty or status_col is None:
            st.info("Call status field not available in returned logs.")
        else:
            grouped = calls.groupby(status_col).size().reset_index(name="calls")
            fig = px.pie(
                grouped,
                names=status_col,
                values="calls",
                hole=0.48,
                color_discrete_sequence=COLOR_SEQUENCE,
            )
            fig.update_layout(margin=dict(l=0, r=0, t=8, b=0), height=360)
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with right:
        st.subheader("Manual rate markers")
        marker_frame = usage_markers[usage_markers["provider"] == "omnidimension"]
        st.dataframe(_display_frame(marker_frame), use_container_width=True, hide_index=True)

    render_dataframe_section("Agents", records.get("agents"))
    render_dataframe_section("Phone numbers", records.get("phone_numbers"))
    render_dataframe_section("Call logs", calls)


def render_titan_email(commitments: pd.DataFrame, assets: pd.DataFrame) -> None:
    st.subheader("Titan / GoDaddy Email")
    titan_assets = assets[assets["provider"] == "godaddy_titan_email"].copy()
    titan_commitments = commitments[commitments["provider"] == "godaddy_titan_email"].copy()
    mailboxes = titan_assets[titan_assets["asset_type"] == "email_mailbox"].copy()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Mailboxes tracked", len(mailboxes))
    col2.metric("Annual email cost", _inr(_decimal_sum(titan_assets.get("annual_amount"))))
    col3.metric("Monthly equivalent", _inr(_decimal_sum(titan_commitments.get("monthly_inr"))))
    col4.metric("Next renewal", _next_renewal_label(titan_commitments))

    left, right = st.columns(2)
    with left:
        st.subheader("Annual cost by mailbox")
        if mailboxes.empty or "annual_amount" not in mailboxes:
            st.info("No mailbox cost data configured.")
        else:
            chart = mailboxes[mailboxes["annual_amount"].notna()].copy()
            chart["annual_amount_float"] = chart["annual_amount"].map(_decimal_to_float)
            fig = px.bar(
                chart,
                x="asset_name",
                y="annual_amount_float",
                color="asset_name",
                color_discrete_sequence=COLOR_SEQUENCE,
                labels={"asset_name": "Mailbox", "annual_amount_float": "Annual INR"},
                text="annual_amount_float",
            )
            _style_bar(fig)
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    with right:
        st.subheader("Storage utilization")
        storage_cols = {"storage_used_mb", "storage_limit_mb"}
        if not storage_cols.issubset(set(mailboxes.columns)):
            st.info(
                "Storage usage is not configured yet. Add storage_used_mb and "
                "storage_limit_mb per mailbox from the GoDaddy/Titan admin export."
            )
        else:
            storage = mailboxes.dropna(subset=["storage_used_mb", "storage_limit_mb"]).copy()
            storage["storage_percent"] = (
                pd.to_numeric(storage["storage_used_mb"])
                / pd.to_numeric(storage["storage_limit_mb"])
                * 100
            )
            fig = px.bar(
                storage,
                x="storage_percent",
                y="asset_name",
                orientation="h",
                color="storage_percent",
                color_continuous_scale="Reds",
                labels={"storage_percent": "Storage used %", "asset_name": "Mailbox"},
            )
            _style_bar(fig)
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.subheader("Email renewal timeline")
    if titan_commitments.empty:
        st.info("No Titan/Email renewals configured.")
    else:
        timeline = titan_commitments.copy()
        timeline["start_date"] = pd.Timestamp.today().date()
        fig = px.timeline(
            timeline,
            x_start="start_date",
            x_end="renewal_date",
            y="name",
            color="record_type",
            hover_data=["monthly_inr", "currency_code", "days_to_renewal"],
            color_discrete_sequence=COLOR_SEQUENCE,
        )
        fig.update_yaxes(autorange="reversed")
        _style_timeline(fig)
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.subheader("Mailbox inventory")
    st.dataframe(_display_frame(mailboxes), use_container_width=True, hide_index=True)


def render_gemini(settings: Any, snapshot: dict[str, Any]) -> None:
    st.subheader("Gemini / Google Cloud")
    google_ready = all(
        [
            settings.google_application_credentials or settings.google_application_credentials_json,
            settings.google_billing_export_project_id,
            settings.google_billing_export_dataset,
            settings.google_billing_export_table,
        ]
    )
    summary = snapshot.get("summary") or {}
    records = snapshot.get("records") or {}
    billing_rows = records.get("billing_rows", pd.DataFrame())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Billing export", "Ready" if google_ready else "Blocked")
    col2.metric("Project ID", settings.google_cloud_project_id or "N/A")
    col3.metric(
        "Current month cost",
        _currency(summary.get("current_month_cost"), summary.get("currency")),
    )
    col4.metric("Project cap", _usd_or_na(summary.get("project_spend_cap_usd")))

    render_snapshot_banner(snapshot)

    if not google_ready:
        st.warning(
            "Google/Gemini charts need Cloud Billing export details before real spend "
            "graphs can be rendered."
        )
    elif billing_rows.empty and snapshot.get("status") == "pass":
        st.info("Billing export is reachable, but no Gemini API cost rows were found yet.")

    limit_col, action_col = st.columns(2)
    with limit_col:
        st.subheader("Spend cap control")
        cap_frame = pd.DataFrame(
            [
                {
                    "control": "Current tracked project cap",
                    "value": settings.google_ai_studio_project_spend_cap_usd,
                    "unit": "USD/month",
                },
                {
                    "control": "Target monthly usage limit",
                    "value": settings.google_ai_studio_monthly_usage_limit_usd,
                    "unit": "USD/month",
                },
            ]
        )
        st.dataframe(_display_frame(cap_frame), use_container_width=True, hide_index=True)
        st.caption(
            "AI Studio project spend caps are edited in AI Studio. The dashboard tracks the "
            "current/target values and links to the control page."
        )
    with action_col:
        st.subheader("Google controls")
        st.link_button("Open AI Studio spend cap", settings.google_ai_studio_spend_url)
        st.link_button("Open AI Studio billing", settings.google_ai_studio_billing_url)

    if not billing_rows.empty:
        daily = _gemini_daily_cost(billing_rows)
        by_sku = _gemini_cost_by_sku(billing_rows)

        left, right = st.columns(2)
        with left:
            st.subheader("Daily Gemini cost")
            fig = px.area(
                daily,
                x="usage_date",
                y="net_cost",
                color_discrete_sequence=["#7c3aed"],
                labels={"usage_date": "Date", "net_cost": f"Net cost ({summary.get('currency')})"},
            )
            _style_line(fig)
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
        with right:
            st.subheader("Cost by model / SKU")
            fig = px.bar(
                by_sku.tail(12),
                x="net_cost",
                y="sku_description",
                orientation="h",
                color="sku_description",
                color_discrete_sequence=COLOR_SEQUENCE,
                labels={
                    "net_cost": f"Net cost ({summary.get('currency')})",
                    "sku_description": "SKU",
                },
                text="net_cost",
            )
            _style_bar(fig, texttemplate="%{x:,.2f}")
            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    reports = pd.DataFrame(
        [
            {
                "report": "Daily Gemini spend in INR",
                "source": "Google Cloud Billing BigQuery export",
                "status": "live_when_export_configured",
            },
            {
                "report": "Spend by model/SKU",
                "source": "Billing export service/SKU fields",
                "status": "live_when_export_configured",
            },
            {
                "report": "Input vs output token trend",
                "source": "Application-side Gemini telemetry",
                "status": "requires_token_logging",
            },
            {
                "report": "Cost per 1K/1M tokens",
                "source": "Billing export + token telemetry",
                "status": "requires_joined_data",
            },
            {
                "report": "Usage spike detection",
                "source": "Daily cost/token aggregates",
                "status": "planned",
            },
        ]
    )
    st.subheader("Gemini report readiness")
    st.dataframe(reports, use_container_width=True, hide_index=True)

    render_dataframe_section("Gemini billing rows", billing_rows)


def render_higgsfield(snapshot: dict[str, Any]) -> None:
    st.subheader("Higgsfield AI")
    render_snapshot_banner(snapshot)
    summary = snapshot.get("summary") or {}
    records = snapshot.get("records") or {}
    metrics = records.get("manual_metrics", pd.DataFrame())
    endpoint_statuses = records.get("endpoint_statuses", pd.DataFrame())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Plan", summary.get("plan_name") or "N/A")
    col2.metric(
        "Current balance",
        _metric_with_unit(summary.get("current_balance"), summary.get("balance_unit") or "credits"),
    )
    col3.metric(
        "Usage this month",
        _metric_with_unit(
            summary.get("usage_this_month"),
            summary.get("balance_unit") or "credits",
        ),
    )
    col4.metric(
        "Monthly limit",
        _metric_with_unit(
            summary.get("monthly_usage_limit"),
            summary.get("balance_unit") or "credits",
        ),
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Usage limit utilization")
        fig = _quota_gauge(
            used=summary.get("usage_this_month"),
            limit=summary.get("monthly_usage_limit"),
        )
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
    with right:
        st.subheader("Cost markers")
        cost_frame = pd.DataFrame(
            [
                {
                    "metric": "monthly_cost",
                    "value": summary.get("monthly_cost"),
                    "unit": summary.get("currency_code"),
                },
                {
                    "metric": "renewal_date",
                    "value": summary.get("renewal_date"),
                    "unit": "",
                },
            ]
        )
        st.dataframe(_display_frame(cost_frame), use_container_width=True, hide_index=True)
        if summary.get("usage_dashboard_url"):
            st.link_button("Open Higgsfield usage", summary["usage_dashboard_url"])
        if summary.get("billing_dashboard_url"):
            st.link_button("Open Higgsfield billing", summary["billing_dashboard_url"])

    if not endpoint_statuses.empty:
        st.subheader("Higgsfield endpoint health")
        st.dataframe(_display_frame(endpoint_statuses), use_container_width=True, hide_index=True)

    render_dataframe_section("Higgsfield manual metrics", metrics)
    for name, frame in records.items():
        if name in {"manual_metrics", "endpoint_statuses"}:
            continue
        render_dataframe_section(f"Higgsfield {name}", frame)


def render_health(
    settings: Any,
    n8n_snapshot: dict[str, Any],
    omni_snapshot: dict[str, Any],
    gemini_snapshot: dict[str, Any],
    higgsfield_snapshot_data: dict[str, Any],
    persistence_status: dict[str, Any],
    fx_rates: pd.DataFrame,
) -> None:
    st.subheader("Configured source statuses")
    status_frame = provider_status_dataframe(settings)
    st.dataframe(_display_frame(status_frame), use_container_width=True, hide_index=True)

    st.subheader("Live dashboard source results")
    frame = pd.DataFrame(
        [
            {
                "provider": "n8n_cloud",
                "dashboard_status": n8n_snapshot.get("status"),
                "error": n8n_snapshot.get("error"),
            },
            {
                "provider": "omnidimension",
                "dashboard_status": omni_snapshot.get("status"),
                "error": omni_snapshot.get("error"),
            },
            {
                "provider": "supabase",
                "dashboard_status": persistence_status.get("status"),
                "error": persistence_status.get("detail", {}).get("error"),
            },
            {
                "provider": "gemini",
                "dashboard_status": gemini_snapshot.get("status"),
                "error": gemini_snapshot.get("error"),
            },
            {
                "provider": "higgsfield_ai",
                "dashboard_status": higgsfield_snapshot_data.get("status"),
                "error": higgsfield_snapshot_data.get("error"),
            },
        ]
    )
    st.dataframe(_display_frame(frame), use_container_width=True, hide_index=True)

    st.subheader("Supabase persistence detail")
    persistence_detail = persistence_status.get("detail") or {}
    detail_frame = pd.DataFrame(
        {"field": key, "value": value}
        for key, value in persistence_detail.items()
        if key != "error"
    )
    st.dataframe(_display_frame(detail_frame), use_container_width=True, hide_index=True)

    st.subheader("Planning FX")
    st.dataframe(_display_frame(fx_rates), use_container_width=True, hide_index=True)


def render_persistence_sidebar(persistence_status: dict[str, Any]) -> None:
    status = persistence_status.get("status")
    message = persistence_status.get("message")
    if status == "connected":
        st.success(f"Persistence: {message}")
    elif status == "warning":
        st.warning(f"Persistence: {message}")
    else:
        st.error(f"Persistence: {message}")


def render_snapshot_banner(snapshot: dict[str, Any]) -> None:
    status = snapshot.get("status")
    error = snapshot.get("error")
    if status == "pass":
        st.success("Live API snapshot loaded.")
    elif status == "partial":
        st.warning(f"Partial API snapshot loaded. {error or ''}")
    elif status == "manual":
        st.info("Manual provider metrics loaded.")
    elif status == "skipped":
        st.info(error or "Source skipped.")
    else:
        st.error(error or "Source failed.")


def render_dataframe_section(title: str, frame: pd.DataFrame | None) -> None:
    with st.expander(title, expanded=False):
        if frame is None or frame.empty:
            st.info(f"No {title.lower()} records returned in this snapshot.")
        else:
            st.dataframe(_display_frame(frame), use_container_width=True, hide_index=True)


def _prepare_n8n_executions(executions: pd.DataFrame, workflows: pd.DataFrame) -> pd.DataFrame:
    if executions.empty:
        return executions
    prepared = executions.copy()
    prepared["started_at_local"] = pd.to_datetime(
        prepared.get("startedAt"), errors="coerce", utc=True
    ).dt.tz_convert("Asia/Kolkata")
    if not workflows.empty and {"id", "name"}.issubset(workflows.columns):
        workflow_map = dict(zip(workflows["id"].astype(str), workflows["name"], strict=False))
        if "workflowId" in prepared:
            prepared["workflow_name"] = prepared["workflowId"].astype(str).map(workflow_map)
    if "workflow_name" not in prepared:
        if "workflowId" in prepared:
            prepared["workflow_name"] = prepared["workflowId"].astype(str)
        else:
            prepared["workflow_name"] = "unknown"
    prepared["workflow_name"] = prepared["workflow_name"].fillna(
        prepared["workflowId"].astype(str) if "workflowId" in prepared else "unknown"
    )
    return prepared


def _prepare_generic_dated_records(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    prepared = frame.copy()
    date_col = _first_existing_column(
        prepared,
        ["created_at", "createdAt", "started_at", "startedAt", "call_time", "timestamp", "date"],
    )
    if date_col:
        prepared["event_time"] = pd.to_datetime(prepared[date_col], errors="coerce", utc=True)
        prepared["event_time"] = prepared["event_time"].dt.tz_convert("Asia/Kolkata")
    return prepared


def _daily_count(frame: pd.DataFrame, date_column: str, value_name: str) -> pd.DataFrame:
    if frame.empty or date_column not in frame:
        return pd.DataFrame(columns=["date", value_name])
    daily = frame.dropna(subset=[date_column]).copy()
    if daily.empty:
        return pd.DataFrame(columns=["date", value_name])
    daily["date"] = pd.to_datetime(daily[date_column]).dt.date
    return daily.groupby("date").size().reset_index(name=value_name).sort_values("date")


def _group_sum(frame: pd.DataFrame, group_col: str, value_col: str) -> pd.DataFrame:
    grouped = frame.dropna(subset=[value_col]).copy()
    grouped[value_col] = grouped[value_col].map(_decimal_to_float)
    return (
        grouped.groupby(group_col, dropna=False)[value_col]
        .sum()
        .reset_index()
        .sort_values(value_col, ascending=True)
    )


def _renewal_month_exposure(commitments: pd.DataFrame) -> pd.DataFrame:
    frame = commitments.dropna(subset=["renewal_date", "monthly_inr"]).copy()
    if frame.empty:
        return frame
    frame["renewal_month"] = pd.to_datetime(frame["renewal_date"]).dt.to_period("M").astype(str)
    frame["monthly_inr"] = frame["monthly_inr"].map(_decimal_to_float)
    return (
        frame.groupby(["renewal_month", "category"], dropna=False)["monthly_inr"]
        .sum()
        .reset_index()
        .sort_values("renewal_month")
    )


def _currency_exposure(commitments: pd.DataFrame) -> pd.DataFrame:
    frame = commitments.dropna(subset=["monthly_amount"]).copy()
    if frame.empty:
        return frame
    frame["monthly_amount"] = frame["monthly_amount"].map(_decimal_to_float)
    return (
        frame.groupby("currency_code", dropna=False)
        .agg(
            commitments=("name", "count"),
            monthly_amount=("monthly_amount", "sum"),
            monthly_inr=("monthly_inr", lambda values: sum(_decimal_to_float(v) for v in values)),
        )
        .reset_index()
    )


def _gemini_daily_cost(frame: pd.DataFrame) -> pd.DataFrame:
    daily = frame.copy()
    daily["usage_date"] = pd.to_datetime(daily["usage_date"], errors="coerce").dt.date
    daily["net_cost"] = pd.to_numeric(daily["net_cost"], errors="coerce").fillna(0)
    return daily.groupby("usage_date")["net_cost"].sum().reset_index().sort_values("usage_date")


def _gemini_cost_by_sku(frame: pd.DataFrame) -> pd.DataFrame:
    by_sku = frame.copy()
    by_sku["net_cost"] = pd.to_numeric(by_sku["net_cost"], errors="coerce").fillna(0)
    return (
        by_sku.groupby("sku_description", dropna=False)["net_cost"]
        .sum()
        .reset_index()
        .sort_values("net_cost", ascending=True)
    )


def _calendar_density(renewals: pd.DataFrame) -> pd.DataFrame:
    frame = renewals.dropna(subset=["renewal_date"]).copy()
    if frame.empty:
        return pd.DataFrame()
    dates = pd.to_datetime(frame["renewal_date"], errors="coerce")
    frame["month"] = dates.dt.strftime("%b %Y")
    frame["day"] = dates.dt.day
    return frame.groupby(["month", "day"]).size().reset_index(name="renewal_count")


def _count_due_soon(frame: pd.DataFrame, days: int) -> int:
    if frame.empty or "days_to_renewal" not in frame:
        return 0
    due = pd.to_numeric(frame["days_to_renewal"], errors="coerce")
    return int(((due >= 0) & (due <= days)).sum())


def _quota_gauge(used: Any, limit: Any) -> go.Figure:
    used_value = _to_float(used)
    limit_value = _to_float(limit)
    if limit_value <= 0:
        limit_value = max(used_value, 1)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=used_value,
            delta={"reference": limit_value, "relative": False},
            gauge={
                "axis": {"range": [0, limit_value]},
                "bar": {"color": "#2563eb"},
                "steps": [
                    {"range": [0, limit_value * 0.7], "color": "#dcfce7"},
                    {"range": [limit_value * 0.7, limit_value * 0.9], "color": "#fef3c7"},
                    {"range": [limit_value * 0.9, limit_value], "color": "#fee2e2"},
                ],
                "threshold": {"line": {"color": "#dc2626", "width": 4}, "value": limit_value},
            },
        )
    )
    fig.update_layout(margin=dict(l=0, r=0, t=8, b=0), height=360)
    return fig


def _markers_dict(markers: pd.DataFrame, provider: str) -> dict[str, Any]:
    if markers.empty:
        return {}
    provider_markers = markers[markers["provider"] == provider]
    return dict(zip(provider_markers["metric_name"], provider_markers["value"], strict=False))


def _first_existing_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def _auto_renew_label(value: Any) -> str:
    if value is True:
        return "Auto-renew on"
    if value is False:
        return "Auto-renew off"
    return "Unknown"


def _urgency_bucket(days: Any) -> str:
    if pd.isna(days):
        return "Unknown"
    days_int = int(days)
    if days_int < 0:
        return "Past due"
    if days_int <= 7:
        return "0-7 days"
    if days_int <= 30:
        return "8-30 days"
    if days_int <= 60:
        return "31-60 days"
    if days_int <= 90:
        return "61-90 days"
    return "90+ days"


def _live_source_count(*snapshots: dict[str, Any]) -> int:
    return sum(1 for snapshot in snapshots if snapshot.get("status") in {"pass", "partial"})


def _next_renewal_label(frame: pd.DataFrame) -> str:
    if frame.empty or "renewal_date" not in frame:
        return "N/A"
    dates = pd.to_datetime(frame["renewal_date"], errors="coerce").dropna()
    if dates.empty:
        return "N/A"
    return dates.min().date().isoformat()


def _decimal_sum(series: Any) -> Decimal:
    if series is None:
        return Decimal("0")
    total = Decimal("0")
    for value in series:
        if isinstance(value, Decimal):
            total += value
        elif value not in (None, "") and not pd.isna(value):
            total += Decimal(str(value))
    return total


def _decimal_to_float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    if value in (None, "") or pd.isna(value):
        return 0.0
    return float(value)


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_decimal_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    formatted = frame.copy()
    for column in formatted.columns:
        if formatted[column].map(lambda value: isinstance(value, Decimal)).any():
            formatted[column] = formatted[column].map(
                lambda value: f"{value:.2f}" if isinstance(value, Decimal) else value
            )
    return formatted


def _display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return streamlit_safe_dataframe(_format_decimal_frame(frame))


def _metric_value(value: Any) -> str:
    if value is None:
        return "N/A"
    return str(value)


def _metric_with_unit(value: Any, unit: str) -> str:
    if value is None:
        return "N/A"
    return f"{value} {unit}"


def _currency(value: Any, currency_code: Any) -> str:
    if value is None:
        return "N/A"
    amount = _to_float(value)
    currency_label = currency_code or ""
    return f"{currency_label} {amount:,.2f}".strip()


def _usd_or_na(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"USD {_to_float(value):,.2f}"


def _inr(value: Decimal | float | int) -> str:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return f"INR {value:,.0f}"


def _style_bar(fig: go.Figure, texttemplate: str | None = None) -> None:
    trace_updates: dict[str, Any] = {"textposition": "outside", "cliponaxis": False}
    if texttemplate:
        trace_updates["texttemplate"] = texttemplate
    fig.update_traces(**trace_updates)
    fig.update_layout(margin=dict(l=0, r=0, t=8, b=0), height=380, showlegend=False)


def _style_line(fig: go.Figure) -> None:
    fig.update_layout(margin=dict(l=0, r=0, t=8, b=0), height=380)
    fig.update_traces(line=dict(width=3))


def _style_timeline(fig: go.Figure) -> None:
    fig.update_layout(margin=dict(l=0, r=0, t=8, b=0), height=420)


if __name__ == "__main__":
    main()
