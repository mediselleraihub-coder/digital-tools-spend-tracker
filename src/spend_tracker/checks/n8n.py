from __future__ import annotations

import httpx

from spend_tracker.checks.base import CheckResult, CheckState, exception_result
from spend_tracker.config import Settings


class N8nCheck:
    provider = "n8n_cloud"

    def run(self, settings: Settings) -> list[CheckResult]:
        if not settings.n8n_base_url or not settings.n8n_api_key:
            return [
                CheckResult(
                    provider=self.provider,
                    check="api_metadata",
                    state=CheckState.SKIP,
                    message="N8N_BASE_URL or N8N_API_KEY is missing",
                )
            ]

        headers = {"X-N8N-API-KEY": settings.n8n_api_key.get_secret_value()}
        base_url = str(settings.n8n_base_url).rstrip("/")
        try:
            with httpx.Client(timeout=20, headers=headers) as client:
                response = client.get(
                    f"{base_url}/api/v1/workflows",
                    params={"limit": "1"},
                )

            if response.status_code == 200:
                payload = response.json()
                sample_count = len(payload.get("data", [])) if isinstance(payload, dict) else None
                return [
                    CheckResult(
                        provider=self.provider,
                        check="api_metadata",
                        state=CheckState.PASS,
                        message="n8n API request succeeded",
                        detail={"sample_workflows": sample_count},
                    )
                ]

            return [
                CheckResult(
                    provider=self.provider,
                    check="api_metadata",
                    state=CheckState.FAIL,
                    message="n8n API request failed",
                    detail={"status_code": response.status_code, "response": response.text[:500]},
                )
            ]
        except Exception as exc:
            return [exception_result(self.provider, "api_metadata", exc)]

