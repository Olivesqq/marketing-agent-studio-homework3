from datetime import timedelta

from app.core.config import Settings
from app.core.models import ModelConnectionRequest, ProviderName
from app.services.security import ModelKeyVault, SessionManager, detect_sensitive_data


def test_dlp_detects_secrets_and_payment_cards():
    assert "api_key" in detect_sensitive_data("api_key=sk-abcdefghijklmnopqrstuvwxyz")
    assert "payment_card" in detect_sensitive_data("测试卡号 4242 4242 4242 4242")
    assert detect_sensitive_data("高价值流失用户召回，复购率提升5%") == []


def test_signed_sessions_reject_tampering(tmp_path):
    settings = Settings(APP_SIGNING_KEY="test-signing-secret", STATE_DB=tmp_path / "state.db", ANALYTICS_DB=tmp_path / "data.db")
    manager = SessionManager(settings)
    token, session_id = manager.issue()
    assert manager.verify(token) == session_id
    assert manager.verify(token + "tampered") is None


def test_model_keys_are_isolated_and_deletable(tmp_path):
    settings = Settings(STATE_DB=tmp_path / "state.db", ANALYTICS_DB=tmp_path / "data.db")
    vault = ModelKeyVault(settings)
    response = vault.create("session-a", ModelConnectionRequest(provider=ProviderName.deepseek, api_key="sk-example-secret-value"))
    assert vault.get("session-a", response.connection_id).api_key == "sk-example-secret-value"
    assert vault.get("session-b", response.connection_id) is None
    assert vault.delete("session-a", response.connection_id) is True
    assert vault.get("session-a", response.connection_id) is None
