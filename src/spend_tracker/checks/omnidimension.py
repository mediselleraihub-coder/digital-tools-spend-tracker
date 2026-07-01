from __future__ import annotations

import httpx

from spend_tracker.checks.base import CheckResult, CheckState, exception_result
from spend_tracker.config import Settings


class OmniDimensionCheck:
    provider = "omnidimension"

    def run(self, settings: Settings) -> list[CheckResult]:
        if not settings.omnidimension_api_base_url or not settings.omnidimension_api_key:
            return [
                CheckResult(
                    provider=self.provider,
                    check="api_metadata",
                    state=CheckState.SKIP,
                    message="OMNIDIMENSION_API_BASE_URL or OMNIDIMENSION_API_KEY is missing",
                )
            ]

        headers = {"Authorization": f"Bearer {settings.omnidimension_api_key.get_secret_value()}"}
        base_url = str(settings.omnidimension_api_base_url).rstrip("/")
        endpoints = {
            "agents": "/agents",
            "phone_numbers": "/phone_number/list",
            "call_logs": "/calls/logs",
        }
        results: list[CheckResult] = []

        try:
            with httpx.Client(timeout=20, headers=headers) as client:
                for check_name, path in endpoints.items():
                    response = client.get(
                        f"{base_url}{path}",
                        params={"pageno": "1", "pagesize": "1"},
                    )
                    if response.status_code == 200:
                        results.append(
                            CheckResult(
                                provider=self.provider,
                                check=check_name,
                                state=CheckState.PASS,
                                message=f"OmniDimension {check_name} endpoint succeeded",
                            )
                        )
                    else:
                        results.append(
                            CheckResult(
                                provider=self.provider,
                                check=check_name,
                                state=CheckState.FAIL,
                                message=f"OmniDimension {check_name} endpoint failed",
                                detail={
                                    "status_code": response.status_code,
                                    "response": response.text[:500],
                                },
                            )
                        )
        except Exception as exc:
            return [exception_result(self.provider, "api_metadata", exc)]

        return results

