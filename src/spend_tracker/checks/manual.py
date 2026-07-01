from __future__ import annotations

from spend_tracker.checks.base import CheckResult, CheckState
from spend_tracker.config import Settings


class ManualProviderCheck:
    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        self._message = message

    def run(self, settings: Settings) -> list[CheckResult]:
        return [
            CheckResult(
                provider=self.provider,
                check="manual_tracking",
                state=CheckState.SKIP,
                message=self._message,
            )
        ]

