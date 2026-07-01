from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from spend_tracker.config import Settings


class CheckState(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class CheckResult:
    provider: str
    check: str
    state: CheckState
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


class ConnectivityCheck(Protocol):
    provider: str

    def run(self, settings: Settings) -> list[CheckResult]:
        """Run the provider check and return structured results."""


def exception_result(provider: str, check: str, exc: Exception) -> CheckResult:
    return CheckResult(
        provider=provider,
        check=check,
        state=CheckState.FAIL,
        message=f"{exc.__class__.__name__}: {exc}",
    )

