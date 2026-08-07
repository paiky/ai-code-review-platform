from __future__ import annotations

import ipaddress
import json
import re
from typing import Any
from urllib.parse import urlparse

from app.core.errors import AppError


DEFAULT_RUNTIME = "CLAUDE_CODE_DEEPSEEK"
CUSTOM_RUNTIME = "OPENAI_RESPONSES_CUSTOM"
RUNTIME_TYPES = frozenset({DEFAULT_RUNTIME, CUSTOM_RUNTIME})
DEFAULT_REVIEW_KEY = "agent-claude-code-deepseek-v4-pro"
CUSTOM_REVIEW_KEY = "agent-openai-responses-custom"
DEFAULT_MODEL = "deepseek-v4-pro[1m]"
CUSTOM_DEFAULT_MODEL = "gpt-5.6-sol"
CUSTOM_DEFAULT_DISPLAY_NAME = "Custom OpenAI Agent"
CUSTOM_REASONING_EFFORTS = ("low", "medium", "high")
RESPONSES_RUNNER_VERSION = "openai-responses-agent-v1"
_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


def normalize_runtime_type(value: Any, *, strict: bool = False) -> str:
    runtime_type = str(value or DEFAULT_RUNTIME).strip().upper()
    if runtime_type in RUNTIME_TYPES:
        return runtime_type
    if strict:
        raise AppError("VALIDATION_ERROR", "selectedRuntime is unsupported", 400)
    return DEFAULT_RUNTIME


def normalize_custom_base_url(value: Any) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text or len(text) > 1024:
        raise AppError("VALIDATION_ERROR", "customRuntime.baseUrl is required", 400)
    parsed = urlparse(text)
    hostname = str(parsed.hostname or "").casefold()
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.port not in {None, 443}
        or not _valid_hostname(hostname)
    ):
        raise AppError(
            "VALIDATION_ERROR",
            "customRuntime.baseUrl must be a safe HTTPS URL without credentials, query, fragment, IP, or custom port",
            400,
        )
    path = parsed.path.rstrip("/")
    return f"https://{hostname}{path}"


def custom_base_url_host(value: Any) -> str | None:
    try:
        return str(urlparse(normalize_custom_base_url(value)).hostname or "").casefold() or None
    except AppError:
        return None


def normalize_worker_capabilities(value: Any, *, legacy_default: bool = True) -> list[str]:
    source = value
    if isinstance(value, str):
        try:
            source = json.loads(value)
        except json.JSONDecodeError:
            source = None
    if not isinstance(source, list):
        return [DEFAULT_RUNTIME] if legacy_default else []
    capabilities = []
    for raw in source:
        item = str(raw or "").strip().upper()
        if item in RUNTIME_TYPES and item not in capabilities:
            capabilities.append(item)
    return capabilities or ([DEFAULT_RUNTIME] if legacy_default else [])


def worker_supports(capabilities_json: Any, runtime_type: str) -> bool:
    return normalize_runtime_type(runtime_type) in normalize_worker_capabilities(capabilities_json)


def runtime_snapshot(record: Any) -> dict[str, Any]:
    runtime_type = normalize_runtime_type(getattr(record, "runtime_type", None))
    if runtime_type == CUSTOM_RUNTIME:
        return {
            "runtimeType": CUSTOM_RUNTIME,
            "wireProtocol": "OPENAI_RESPONSES",
            "displayName": str(
                getattr(record, "custom_display_name", None) or CUSTOM_DEFAULT_DISPLAY_NAME
            ),
            "baseUrl": str(getattr(record, "custom_base_url", None) or ""),
            "model": str(getattr(record, "custom_model", None) or CUSTOM_DEFAULT_MODEL),
            "reasoningEffort": str(
                getattr(record, "custom_reasoning_effort", None) or "high"
            ),
            "tlsVerify": getattr(record, "custom_tls_verify", None) is not False,
            "credentialSlot": "CUSTOM_OPENAI",
        }
    return {
        "runtimeType": DEFAULT_RUNTIME,
        "wireProtocol": "ANTHROPIC_COMPATIBLE",
        "displayName": "Claude Code + DeepSeek",
        "baseUrl": "https://api.deepseek.com/anthropic",
        "model": DEFAULT_MODEL,
        "reasoningEffort": "high",
        "credentialSlot": "DEEPSEEK",
    }


def _valid_hostname(value: str) -> bool:
    if not value or "*" in value or not _HOSTNAME.fullmatch(value):
        return False
    try:
        ipaddress.ip_address(value)
        return False
    except ValueError:
        return "." in value
