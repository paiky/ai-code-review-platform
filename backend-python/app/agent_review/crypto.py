from __future__ import annotations

import hashlib

from app.core.config import get_settings
from app.core.errors import AppError


def encrypt_api_key(value: str) -> tuple[str, str]:
    key = str(value or "").strip()
    if not key:
        raise AppError("VALIDATION_ERROR", "Agent API Key cannot be empty", 400)
    cipher = _fernet()
    ciphertext = cipher.encrypt(key.encode("utf-8")).decode("ascii")
    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return ciphertext, fingerprint


def decrypt_api_key(ciphertext: str | None) -> str:
    if not ciphertext:
        raise AppError("AGENT_API_KEY_UNAVAILABLE", "Agent API Key is not configured", 409)
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except AppError:
        raise
    except Exception as exception:
        raise AppError(
            "AGENT_API_KEY_DECRYPT_FAILED",
            "Agent API Key cannot be decrypted with the configured master key",
            409,
        ) from exception


def encryption_available() -> bool:
    try:
        _fernet()
        return True
    except AppError:
        return False


def mask_fingerprint(fingerprint: str | None) -> str | None:
    return f"configured:{fingerprint}" if fingerprint else None


def _fernet():
    key = get_settings().agent_review_config_encryption_key.strip()
    if not key:
        raise AppError(
            "AGENT_ENCRYPTION_KEY_UNAVAILABLE",
            "AGENT_REVIEW_CONFIG_ENCRYPTION_KEY is not configured",
            409,
        )
    try:
        from cryptography.fernet import Fernet

        return Fernet(key.encode("ascii"))
    except AppError:
        raise
    except Exception as exception:
        raise AppError(
            "AGENT_ENCRYPTION_KEY_UNAVAILABLE",
            "AGENT_REVIEW_CONFIG_ENCRYPTION_KEY is invalid",
            409,
        ) from exception
