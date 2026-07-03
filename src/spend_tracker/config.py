from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import AnyUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        populate_by_name=True,
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    refresh_interval_hours: int = Field(default=6, alias="REFRESH_INTERVAL_HOURS")
    default_currency: str = Field(default="INR", alias="DEFAULT_CURRENCY")
    timezone: str = Field(default="Asia/Kolkata", alias="TIMEZONE")

    supabase_url: AnyUrl = Field(alias="SUPABASE_URL")
    supabase_anon_key: SecretStr | None = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: SecretStr | None = Field(
        default=None, alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    supabase_db_password: SecretStr = Field(alias="SUPABASE_DB_PASSWORD")
    supabase_db_host: str = Field(alias="SUPABASE_DB_HOST")
    supabase_db_port: int = Field(default=5432, alias="SUPABASE_DB_PORT")
    supabase_db_name: str = Field(default="postgres", alias="SUPABASE_DB_NAME")
    supabase_db_user: str = Field(default="postgres", alias="SUPABASE_DB_USER")

    google_cloud_project_id: str | None = Field(default=None, alias="GOOGLE_CLOUD_PROJECT_ID")
    google_application_credentials: str | None = Field(
        default=None, alias="GOOGLE_APPLICATION_CREDENTIALS"
    )
    google_application_credentials_json: SecretStr | None = Field(
        default=None, alias="GOOGLE_APPLICATION_CREDENTIALS_JSON"
    )
    google_billing_export_project_id: str | None = Field(
        default=None, alias="GOOGLE_BILLING_EXPORT_PROJECT_ID"
    )
    google_billing_export_dataset: str | None = Field(
        default=None, alias="GOOGLE_BILLING_EXPORT_DATASET"
    )
    google_billing_export_table: str | None = Field(
        default=None, alias="GOOGLE_BILLING_EXPORT_TABLE"
    )
    google_cloud_billing_account_id: str | None = Field(
        default=None, alias="GOOGLE_CLOUD_BILLING_ACCOUNT_ID"
    )
    google_ai_studio_project_spend_cap_usd: str | None = Field(
        default=None, alias="GOOGLE_AI_STUDIO_PROJECT_SPEND_CAP_USD"
    )
    google_ai_studio_monthly_usage_limit_usd: str | None = Field(
        default=None, alias="GOOGLE_AI_STUDIO_MONTHLY_USAGE_LIMIT_USD"
    )
    google_ai_studio_spend_url: str = Field(
        default="https://aistudio.google.com/app/spend",
        alias="GOOGLE_AI_STUDIO_SPEND_URL",
    )
    google_ai_studio_billing_url: str = Field(
        default="https://aistudio.google.com/app/billing",
        alias="GOOGLE_AI_STUDIO_BILLING_URL",
    )

    openai_admin_api_key: SecretStr | None = Field(default=None, alias="OPENAI_ADMIN_API_KEY")
    openai_org_id: str | None = Field(default=None, alias="OPENAI_ORG_ID")
    openai_plan_name: str | None = Field(default=None, alias="OPENAI_PLAN_NAME")
    openai_monthly_cost: str | None = Field(default=None, alias="OPENAI_MONTHLY_COST")
    openai_renewal_date: str | None = Field(default=None, alias="OPENAI_RENEWAL_DATE")
    openai_billing_source: str | None = Field(default=None, alias="OPENAI_BILLING_SOURCE")

    anthropic_admin_api_key: SecretStr | None = Field(
        default=None, alias="ANTHROPIC_ADMIN_API_KEY"
    )
    anthropic_workspace_id: str | None = Field(default=None, alias="ANTHROPIC_WORKSPACE_ID")
    anthropic_plan_name: str | None = Field(default=None, alias="ANTHROPIC_PLAN_NAME")
    anthropic_monthly_cost: str | None = Field(default=None, alias="ANTHROPIC_MONTHLY_COST")
    anthropic_renewal_date: str | None = Field(default=None, alias="ANTHROPIC_RENEWAL_DATE")
    anthropic_billing_source: str | None = Field(default=None, alias="ANTHROPIC_BILLING_SOURCE")
    anthropic_usage_credits_balance: str | None = Field(
        default=None, alias="ANTHROPIC_USAGE_CREDITS_BALANCE"
    )
    anthropic_auto_reload_enabled: bool | None = Field(
        default=None, alias="ANTHROPIC_AUTO_RELOAD_ENABLED"
    )

    n8n_base_url: AnyUrl | None = Field(default=None, alias="N8N_BASE_URL")
    n8n_api_key: SecretStr | None = Field(default=None, alias="N8N_API_KEY")
    n8n_monthly_cost: str | None = Field(default=None, alias="N8N_MONTHLY_COST")
    n8n_renewal_date: str | None = Field(default=None, alias="N8N_RENEWAL_DATE")
    n8n_execution_limit: int | None = Field(default=None, alias="N8N_EXECUTION_LIMIT")

    omnidimension_api_base_url: AnyUrl | None = Field(
        default=None, alias="OMNIDIMENSION_API_BASE_URL"
    )
    omnidimension_api_key: SecretStr | None = Field(
        default=None, alias="OMNIDIMENSION_API_KEY"
    )
    omnidimension_monthly_cost: str | None = Field(
        default=None, alias="OMNIDIMENSION_MONTHLY_COST"
    )
    omnidimension_renewal_date: str | None = Field(
        default=None, alias="OMNIDIMENSION_RENEWAL_DATE"
    )

    bigrock_customer_id: str | None = Field(default=None, alias="BIGROCK_CUSTOMER_ID")
    bigrock_api_key: SecretStr | None = Field(default=None, alias="BIGROCK_API_KEY")

    titan_api_base_url: AnyUrl | None = Field(default=None, alias="TITAN_API_BASE_URL")
    titan_api_key: SecretStr | None = Field(default=None, alias="TITAN_API_KEY")
    titan_monthly_cost: str | None = Field(default=None, alias="TITAN_MONTHLY_COST")
    titan_renewal_date: str | None = Field(default=None, alias="TITAN_RENEWAL_DATE")

    higgsfield_plan_name: str | None = Field(default=None, alias="HIGGSFIELD_PLAN_NAME")
    higgsfield_monthly_cost: str | None = Field(default=None, alias="HIGGSFIELD_MONTHLY_COST")
    higgsfield_currency_code: str | None = Field(default="USD", alias="HIGGSFIELD_CURRENCY_CODE")
    higgsfield_renewal_date: str | None = Field(default=None, alias="HIGGSFIELD_RENEWAL_DATE")
    higgsfield_current_balance: str | None = Field(default=None, alias="HIGGSFIELD_CURRENT_BALANCE")
    higgsfield_balance_unit: str = Field(default="credits", alias="HIGGSFIELD_BALANCE_UNIT")
    higgsfield_monthly_usage_limit: str | None = Field(
        default=None, alias="HIGGSFIELD_MONTHLY_USAGE_LIMIT"
    )
    higgsfield_usage_this_month: str | None = Field(
        default=None, alias="HIGGSFIELD_USAGE_THIS_MONTH"
    )
    higgsfield_usage_dashboard_url: str | None = Field(
        default=None, alias="HIGGSFIELD_USAGE_DASHBOARD_URL"
    )
    higgsfield_billing_dashboard_url: str | None = Field(
        default=None, alias="HIGGSFIELD_BILLING_DASHBOARD_URL"
    )
    higgsfield_api_base: AnyUrl | None = Field(
        default="https://fnf.higgsfield.ai",
        alias="HIGGSFIELD_API_BASE",
    )
    higgsfield_bearer_token: SecretStr | None = Field(
        default=None,
        alias="HIGGSFIELD_BEARER_TOKEN",
    )
    higgsfield_cookie: SecretStr | None = Field(
        default=None,
        alias="HIGGSFIELD_COOKIE",
    )
    higgsfield_extra_headers_json: SecretStr | None = Field(
        default=None,
        alias="HIGGSFIELD_EXTRA_HEADERS_JSON",
    )

    @field_validator("*", mode="before")
    @classmethod
    def blank_strings_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def supabase_rest_url(self) -> str:
        return f"{str(self.supabase_url).rstrip('/')}/rest/v1"


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    load_dotenv(ENV_PATH, override=False)
    return Settings()
