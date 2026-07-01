from __future__ import annotations

from spend_tracker.checks.base import CheckResult, CheckState, ConnectivityCheck
from spend_tracker.checks.google_bigquery import GoogleBigQueryCheck
from spend_tracker.checks.manual import ManualProviderCheck
from spend_tracker.checks.n8n import N8nCheck
from spend_tracker.checks.omnidimension import OmniDimensionCheck
from spend_tracker.checks.supabase import SupabaseCheck


def all_checks() -> list[ConnectivityCheck]:
    return [
        SupabaseCheck(),
        N8nCheck(),
        OmniDimensionCheck(),
        GoogleBigQueryCheck(),
        ManualProviderCheck(
            "openai",
            "ChatGPT Plus is tracked as manual subscription; platform billing API skipped",
        ),
        ManualProviderCheck(
            "anthropic",
            "Claude Pro is tracked as manual subscription; Console Admin API skipped",
        ),
        ManualProviderCheck(
            "bigrock",
            "BigRock is tracked from downloaded transactions CSV and dashboard renewals",
        ),
        ManualProviderCheck(
            "titan_email",
            "GoDaddy/Titan email is tracked as annual manual subscription/assets",
        ),
    ]


__all__ = ["CheckResult", "CheckState", "ConnectivityCheck", "all_checks"]

