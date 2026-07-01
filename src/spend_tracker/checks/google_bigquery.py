from __future__ import annotations

from pathlib import Path

from google.cloud import bigquery

from spend_tracker.checks.base import CheckResult, CheckState, exception_result
from spend_tracker.config import Settings


class GoogleBigQueryCheck:
    provider = "google_cloud"

    def run(self, settings: Settings) -> list[CheckResult]:
        missing = [
            name
            for name, value in {
                "GOOGLE_APPLICATION_CREDENTIALS": settings.google_application_credentials,
                "GOOGLE_BILLING_EXPORT_PROJECT_ID": settings.google_billing_export_project_id,
                "GOOGLE_BILLING_EXPORT_DATASET": settings.google_billing_export_dataset,
                "GOOGLE_BILLING_EXPORT_TABLE": settings.google_billing_export_table,
            }.items()
            if not value
        ]
        if missing:
            return [
                CheckResult(
                    provider=self.provider,
                    check="billing_export",
                    state=CheckState.SKIP,
                    message="Google Billing BigQuery export is not fully configured",
                    detail={"missing_env": missing},
                )
            ]

        credentials_path = Path(settings.google_application_credentials or "")
        if not credentials_path.exists():
            return [
                CheckResult(
                    provider=self.provider,
                    check="billing_export",
                    state=CheckState.FAIL,
                    message="GOOGLE_APPLICATION_CREDENTIALS path does not exist",
                    detail={"path": str(credentials_path)},
                )
            ]

        table_id = (
            f"{settings.google_billing_export_project_id}."
            f"{settings.google_billing_export_dataset}."
            f"{settings.google_billing_export_table}"
        )

        try:
            client = bigquery.Client(project=settings.google_billing_export_project_id)
            table = client.get_table(table_id)
            return [
                CheckResult(
                    provider=self.provider,
                    check="billing_export",
                    state=CheckState.PASS,
                    message="Google Billing BigQuery export table is reachable",
                    detail={
                        "table": table_id,
                        "schema_fields": len(table.schema),
                        "num_rows": table.num_rows,
                    },
                )
            ]
        except Exception as exc:
            return [exception_result(self.provider, "billing_export", exc)]

