"""Environment settings; loading configuration never contacts Groww."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    service_api_key: SecretStr | None = Field(default=None, repr=False)
    groww_auth_method: Literal["api_key", "totp"] = "api_key"
    groww_api_key: SecretStr | None = Field(default=None, repr=False)
    groww_api_secret: SecretStr | None = Field(default=None, repr=False)
    groww_totp_secret: SecretStr | None = Field(default=None, repr=False)
    groww_request_timeout_seconds: float = Field(default=10, gt=0, le=60, allow_inf_nan=False)

    @field_validator(
        "service_api_key", "groww_api_key", "groww_api_secret", "groww_totp_secret", mode="before"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
