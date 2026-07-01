from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from spend_tracker.config import Settings


class SourceStatus(StrEnum):
    API_READY = "api_ready"
    MANUAL_SUBSCRIPTION = "manual_subscription"
    MANUAL_CSV = "manual_csv"
    BLOCKED_MISSING_CREDENTIALS = "blocked_missing_credentials"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    status: SourceStatus
    reason: str


def classify_providers(settings: Settings) -> list[ProviderStatus]:
    google_ready = all(
        [
            settings.google_application_credentials,
            settings.google_billing_export_project_id,
            settings.google_billing_export_dataset,
            settings.google_billing_export_table,
        ]
    )

    return [
        ProviderStatus("supabase", SourceStatus.API_READY, "Supabase DB settings are configured"),
        ProviderStatus(
            "google_cloud",
            SourceStatus.API_READY if google_ready else SourceStatus.BLOCKED_MISSING_CREDENTIALS,
            "BigQuery billing export is complete"
            if google_ready
            else "Google billing export credentials, dataset, or table are incomplete",
        ),
        ProviderStatus(
            "gemini",
            SourceStatus.API_READY if google_ready else SourceStatus.BLOCKED_MISSING_CREDENTIALS,
            "Gemini costs flow through Google Cloud Billing export"
            if google_ready
            else "Gemini billing waits on Google Cloud Billing export readiness",
        ),
        ProviderStatus(
            "openai",
            SourceStatus.MANUAL_SUBSCRIPTION,
            "ChatGPT Plus subscription; OpenAI Platform API billing is not applicable",
        ),
        ProviderStatus(
            "anthropic",
            SourceStatus.MANUAL_SUBSCRIPTION,
            "Claude Pro subscription; Anthropic Console API billing is not applicable",
        ),
        ProviderStatus(
            "n8n_cloud",
            SourceStatus.API_READY
            if settings.n8n_base_url and settings.n8n_api_key
            else SourceStatus.BLOCKED_MISSING_CREDENTIALS,
            "n8n API key and base URL are configured"
            if settings.n8n_base_url and settings.n8n_api_key
            else "n8n API key or base URL is missing",
        ),
        ProviderStatus(
            "omnidimension",
            SourceStatus.API_READY
            if settings.omnidimension_api_base_url and settings.omnidimension_api_key
            else SourceStatus.BLOCKED_MISSING_CREDENTIALS,
            "OmniDimension API key and base URL are configured"
            if settings.omnidimension_api_base_url and settings.omnidimension_api_key
            else "OmniDimension API key or base URL is missing",
        ),
        ProviderStatus(
            "bigrock",
            SourceStatus.MANUAL_CSV,
            "BigRock is tracked from downloaded transaction CSVs and dashboard renewals",
        ),
        ProviderStatus(
            "titan_email",
            SourceStatus.MANUAL_SUBSCRIPTION,
            "GoDaddy/Titan email is tracked as annual manual subscription/assets",
        ),
    ]

