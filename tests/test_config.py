import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_settings_work_without_groww_credentials():
    settings = Settings()
    assert settings.groww_auth_method == "api_key"
    assert settings.groww_api_key is None
    assert settings.service_api_key is None


def test_dotenv_and_environment_precedence(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "GROWW_AUTH_METHOD=totp\nGROWW_API_KEY=synthetic-token\nSERVICE_API_KEY=\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GROWW_AUTH_METHOD", "api_key")
    settings = Settings()
    assert settings.groww_auth_method == "api_key"
    assert settings.groww_api_key.get_secret_value() == "synthetic-token"
    assert settings.service_api_key is None


def test_settings_hide_secrets(monkeypatch):
    monkeypatch.setenv("GROWW_API_SECRET", "synthetic-private-value")
    settings = Settings()
    assert "synthetic-private-value" not in repr(settings)
    assert "synthetic-private-value" not in settings.model_dump_json()


@pytest.mark.parametrize("value", ["0", "-1", "61", "nan", "inf", "invalid"])
def test_timeout_validation(value, monkeypatch):
    monkeypatch.setenv("GROWW_REQUEST_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_auth_method_is_rejected(monkeypatch):
    monkeypatch.setenv("GROWW_AUTH_METHOD", "unsupported")
    with pytest.raises(ValidationError):
        Settings()


def test_short_service_key_error_hides_input(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", "synthetic-short")
    with pytest.raises(ValidationError) as caught:
        Settings()
    assert "synthetic-short" not in str(caught.value)


def test_configuration_is_cached():
    assert get_settings() is get_settings()
