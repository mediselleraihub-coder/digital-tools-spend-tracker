from __future__ import annotations

from spend_tracker.config import Settings
from spend_tracker.provider_status import SourceStatus, classify_providers


def make_settings(**overrides: object) -> Settings:
    values = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_DB_PASSWORD": "password",
        "SUPABASE_DB_HOST": "db.example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service",
        "N8N_BASE_URL": "https://example.app.n8n.cloud",
        "N8N_API_KEY": "n8n",
        "OMNIDIMENSION_API_BASE_URL": "https://backend.omnidim.io/api/v1",
        "OMNIDIMENSION_API_KEY": "omni",
    }
    values.update(overrides)
    return Settings(**values)


def test_google_is_blocked_when_export_table_missing() -> None:
    settings = make_settings(
        GOOGLE_APPLICATION_CREDENTIALS="/tmp/creds.json",
        GOOGLE_BILLING_EXPORT_PROJECT_ID="project",
        GOOGLE_BILLING_EXPORT_DATASET="dataset",
        GOOGLE_BILLING_EXPORT_TABLE="",
    )

    statuses = {status.provider: status for status in classify_providers(settings)}

    assert statuses["google_cloud"].status == SourceStatus.BLOCKED_MISSING_CREDENTIALS
    assert statuses["gemini"].status == SourceStatus.BLOCKED_MISSING_CREDENTIALS


def test_manual_subscriptions_are_not_api_ready() -> None:
    statuses = {status.provider: status for status in classify_providers(make_settings())}

    assert statuses["openai"].status == SourceStatus.MANUAL_SUBSCRIPTION
    assert statuses["anthropic"].status == SourceStatus.MANUAL_SUBSCRIPTION
    assert statuses["bigrock"].status == SourceStatus.MANUAL_CSV

