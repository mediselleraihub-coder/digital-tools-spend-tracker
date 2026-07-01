from __future__ import annotations

import httpx
import psycopg
from psycopg.rows import dict_row

from spend_tracker.checks.base import CheckResult, CheckState, exception_result
from spend_tracker.config import Settings

EXPECTED_TABLES = {
    "alert_events",
    "alert_rules",
    "assets",
    "fx_rates",
    "ingestion_cursors",
    "ingestion_runs",
    "products",
    "provider_credentials_metadata",
    "subscriptions",
    "usage_costs",
    "vendors",
}


class SupabaseCheck:
    provider = "supabase"

    def run(self, settings: Settings) -> list[CheckResult]:
        return [self._check_postgres(settings), self._check_service_rest(settings)]

    def _check_postgres(self, settings: Settings) -> CheckResult:
        try:
            with psycopg.connect(
                host=settings.supabase_db_host,
                port=settings.supabase_db_port,
                dbname=settings.supabase_db_name,
                user=settings.supabase_db_user,
                password=settings.supabase_db_password.get_secret_value(),
                sslmode="require",
                connect_timeout=10,
                row_factory=dict_row,
            ) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = 'digital_spend'
                      and table_type = 'BASE TABLE'
                    order by table_name
                    """
                )
                tables = {row["table_name"] for row in cur.fetchall()}
                missing = sorted(EXPECTED_TABLES - tables)
                if missing:
                    return CheckResult(
                        provider=self.provider,
                        check="postgres_schema",
                        state=CheckState.FAIL,
                        message="connected, but expected digital_spend tables are missing",
                        detail={"missing_tables": missing, "found_tables": sorted(tables)},
                    )

                cur.execute("select digital_spend.fn_current_actor() as actor")
                actor = cur.fetchone()["actor"]

            return CheckResult(
                provider=self.provider,
                check="postgres_schema",
                state=CheckState.PASS,
                message="connected to Supabase Postgres and found expected tables",
                detail={"table_count": len(EXPECTED_TABLES), "actor_available": actor is not None},
            )
        except Exception as exc:
            return exception_result(self.provider, "postgres_schema", exc)

    def _check_service_rest(self, settings: Settings) -> CheckResult:
        if not settings.supabase_service_role_key:
            return CheckResult(
                provider=self.provider,
                check="service_role_rest",
                state=CheckState.SKIP,
                message="SUPABASE_SERVICE_ROLE_KEY is missing",
            )

        token = settings.supabase_service_role_key.get_secret_value()
        headers = {
            "apikey": token,
            "Authorization": f"Bearer {token}",
            "Accept-Profile": "digital_spend",
        }

        try:
            with httpx.Client(timeout=15) as client:
                response = client.get(
                    f"{settings.supabase_rest_url}/vendors",
                    params={"select": "vendor_id", "limit": "1"},
                    headers=headers,
                )
            if response.status_code == 200:
                return CheckResult(
                    provider=self.provider,
                    check="service_role_rest",
                    state=CheckState.PASS,
                    message="service-role REST request succeeded for digital_spend.vendors",
                )

            state = (
                CheckState.WARN
                if response.status_code in {401, 403, 404, 406}
                else CheckState.FAIL
            )
            return CheckResult(
                provider=self.provider,
                check="service_role_rest",
                state=state,
                message="service-role REST request did not succeed",
                detail={"status_code": response.status_code, "response": response.text[:500]},
            )
        except Exception as exc:
            return exception_result(self.provider, "service_role_rest", exc)
