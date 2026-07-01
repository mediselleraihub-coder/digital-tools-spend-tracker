from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from spend_tracker.checks import CheckResult, CheckState, all_checks
from spend_tracker.config import load_settings
from spend_tracker.provider_status import classify_providers

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(prog="spend-tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Run provider connectivity checks")
    check_parser.add_argument("--provider", help="Provider slug to check")
    check_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    status_parser = subparsers.add_parser("status", help="Classify provider source statuses")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    args = parser.parse_args()

    try:
        settings = load_settings()
    except ValidationError as exc:
        console.print("[red]Configuration validation failed[/red]")
        console.print(exc)
        return 2

    if args.command == "check":
        results = run_checks(provider=args.provider)
        if args.json:
            print(json.dumps([asdict(result) for result in results], indent=2, default=str))
        else:
            render_check_results(results)
        return 1 if any(result.state == CheckState.FAIL for result in results) else 0

    if args.command == "status":
        statuses = classify_providers(settings)
        if args.json:
            print(json.dumps([asdict(status) for status in statuses], indent=2, default=str))
        else:
            render_provider_statuses(statuses)
        return 0

    parser.error("unknown command")
    return 2


def run_checks(provider: str | None = None) -> list[CheckResult]:
    settings = load_settings()
    checks = all_checks()
    if provider:
        checks = [check for check in checks if check.provider == provider]
        if not checks:
            return [
                CheckResult(
                    provider=provider,
                    check="selection",
                    state=CheckState.FAIL,
                    message="unknown provider",
                )
            ]

    results: list[CheckResult] = []
    for check in checks:
        results.extend(check.run(settings))
    return results


def render_check_results(results: list[CheckResult]) -> None:
    table = Table(title="Digital Tools Spend Tracker Connectivity")
    table.add_column("Provider", no_wrap=True)
    table.add_column("Check", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("Message")

    style_by_state = {
        CheckState.PASS: "green",
        CheckState.WARN: "yellow",
        CheckState.FAIL: "red",
        CheckState.SKIP: "cyan",
    }
    for result in results:
        style = style_by_state[result.state]
        table.add_row(
            result.provider,
            result.check,
            f"[{style}]{result.state.value}[/{style}]",
            result.message,
        )
    console.print(table)


def render_provider_statuses(statuses: object) -> None:
    table = Table(title="Provider Source Status")
    table.add_column("Provider", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Reason")
    for status in statuses:
        table.add_row(status.provider, status.status.value, status.reason)
    console.print(table)


if __name__ == "__main__":
    raise SystemExit(main())

