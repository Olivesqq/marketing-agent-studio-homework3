from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.config import Settings
from app.core.models import ModelConnectionRequest, ModelConnectionResponse, ProviderName


PROVIDER_PRESETS = {
    ProviderName.openai: {
        "label": "OpenAI",
        "default_model": "gpt-5.4-mini",
        "api_base": "https://api.openai.com/v1",
        "protocol": "responses",
    },
    ProviderName.qwen: {
        "label": "通义千问（DashScope）",
        "default_model": "qwen-plus",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "protocol": "chat_completions",
    },
    ProviderName.deepseek: {
        "label": "DeepSeek",
        "default_model": "deepseek-chat",
        "api_base": "https://api.deepseek.com/v1",
        "protocol": "chat_completions",
    },
}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class SessionManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    def verify_access_code(self, candidate: str) -> bool:
        if self.settings.DEMO_ACCESS_CODE_HASH:
            try:
                scheme, iterations, salt, expected = self.settings.DEMO_ACCESS_CODE_HASH.split("$", 3)
                if scheme != "pbkdf2_sha256":
                    return False
                digest = hashlib.pbkdf2_hmac("sha256", candidate.encode(), salt.encode(), int(iterations))
                return hmac.compare_digest(_b64(digest), expected)
            except (ValueError, TypeError):
                return False
        return hmac.compare_digest(candidate, self.settings.DEMO_ACCESS_CODE)

    def issue(self) -> tuple[str, str]:
        session_id = secrets.token_urlsafe(24)
        expires = int(time.time()) + self.settings.SESSION_TTL_MINUTES * 60
        payload = f"{session_id}.{expires}"
        signature = hmac.new(self.settings.APP_SIGNING_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}", session_id

    def verify(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            session_id, expires, signature = token.rsplit(".", 2)
            payload = f"{session_id}.{expires}"
            expected = hmac.new(self.settings.APP_SIGNING_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected) or int(expires) < int(time.time()):
                return None
            return session_id
        except (ValueError, TypeError):
            return None


@dataclass
class _SecretConnection:
    session_id: str
    provider: ProviderName
    api_key: str
    model: str
    expires_at: datetime


class ModelKeyVault:
    """Process-memory-only BYOK vault. Keys never enter SQLite, events or exports."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._items: dict[str, _SecretConnection] = {}
        self._lock = threading.RLock()

    def create(self, session_id: str, request: ModelConnectionRequest) -> ModelConnectionResponse:
        preset = PROVIDER_PRESETS[request.provider]
        connection_id = "MC_" + secrets.token_urlsafe(18)
        expires_at = datetime.utcnow() + timedelta(minutes=self.settings.MODEL_KEY_TTL_MINUTES)
        item = _SecretConnection(
            session_id=session_id,
            provider=request.provider,
            api_key=request.api_key.strip(),
            model=request.model or preset["default_model"],
            expires_at=expires_at,
        )
        with self._lock:
            self._purge()
            self._items[connection_id] = item
        fingerprint = hashlib.sha256(item.api_key.encode()).hexdigest()[:8]
        return ModelConnectionResponse(
            connection_id=connection_id,
            provider=item.provider,
            model=item.model,
            expires_at=expires_at,
            key_fingerprint=f"sha256:{fingerprint}",
        )

    def get(self, session_id: str, connection_id: str) -> _SecretConnection | None:
        with self._lock:
            self._purge()
            item = self._items.get(connection_id)
            return item if item and item.session_id == session_id else None

    def delete(self, session_id: str, connection_id: str) -> bool:
        with self._lock:
            item = self._items.get(connection_id)
            if not item or item.session_id != session_id:
                return False
            del self._items[connection_id]
            return True

    def _purge(self) -> None:
        now = datetime.utcnow()
        for key in [key for key, value in self._items.items() if value.expires_at <= now]:
            del self._items[key]


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, identity: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[identity]
            while bucket and bucket[0] < now - self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True


_SECRET_PATTERNS = {
    "api_key": re.compile(r"(?i)(?:sk-[A-Za-z0-9_-]{16,}|api[_ -]?key\s*[:=]\s*\S{8,})"),
    "password": re.compile(r"(?i)(?:password|密码|口令)\s*[:=：]\s*\S{4,}"),
    "email": re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "national_id": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
}


def _luhn(number: str) -> bool:
    digits = [int(ch) for ch in number]
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def detect_sensitive_data(text: str) -> list[str]:
    findings = [name for name, pattern in _SECRET_PATTERNS.items() if pattern.search(text)]
    for candidate in re.findall(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", text):
        compact = re.sub(r"\D", "", candidate)
        if 13 <= len(compact) <= 19 and _luhn(compact):
            findings.append("payment_card")
            break
    return sorted(set(findings))


def redact(text: str) -> str:
    result = text
    for name, pattern in _SECRET_PATTERNS.items():
        result = pattern.sub(f"[REDACTED_{name.upper()}]", result)
    return result
