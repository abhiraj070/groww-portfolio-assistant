"""Environment settings; loading configuration never contacts Groww."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    service_api_key: SecretStr | None = Field(default=None, repr=False)
    mcp_bearer_token: SecretStr | None = Field(default=None, repr=False)
    mcp_public_url: AnyHttpUrl | None = None
    render_external_url: AnyHttpUrl | None = None
    valuation_exchange: Literal["NSE", "BSE"] = "NSE"
    sector_metadata_file: Path | None = None
    ledger_path: Path = Path("data/investments.sqlite3")
    api_requests_per_minute: int = Field(default=300, ge=1, le=10000)
    groww_auth_method: Literal["api_key", "totp"] = "api_key"
    groww_api_key: SecretStr | None = Field(default=None, repr=False)
    groww_api_secret: SecretStr | None = Field(default=None, repr=False)
    groww_totp_secret: SecretStr | None = Field(default=None, repr=False)
    groww_request_timeout_seconds: float = Field(default=10, gt=0, le=60, allow_inf_nan=False)

    @field_validator(
        "service_api_key",
        "mcp_bearer_token",
        "groww_api_key",
        "groww_api_secret",
        "groww_totp_secret",
        mode="before",
    )
    @classmethod
    def empty_secret_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("service_api_key")
    @classmethod
    def validate_service_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("SERVICE_API_KEY must contain at least 32 characters")
        return value

    @field_validator("mcp_bearer_token")
    @classmethod
    def validate_mcp_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and (
            len(value.get_secret_value()) < 32 or any(c.isspace() for c in value.get_secret_value())
        ):
            raise ValueError("MCP_BEARER_TOKEN must contain at least 32 non-whitespace characters")
        return value

    @field_validator("mcp_public_url", "render_external_url")
    @classmethod
    def validate_mcp_origin(cls, value: AnyHttpUrl | None):
        if value is None:
            return value
        if (
            value.username
            or value.password
            or value.query
            or value.fragment
            or value.path not in {"", "/"}
        ):
            raise ValueError("MCP public URL must be an origin without credentials, path or query")
        if value.scheme != "https" and value.host not in {"localhost", "127.0.0.1", "[::1]"}:
            raise ValueError("Hosted MCP requires an HTTPS public URL")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
