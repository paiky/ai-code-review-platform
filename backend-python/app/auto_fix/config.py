import os
from pathlib import Path

from app.core.config import get_settings


def gitlab_webhook_token() -> str:
    return os.getenv("AUTO_FIX_GITLAB_WEBHOOK_TOKEN", "").strip()


def provider_code(default_code: str) -> str:
    return (os.getenv("AUTO_FIX_PROVIDER_CODE", "").strip() or default_code).upper()


def workspace_root() -> Path:
    configured_root = os.getenv("AUTO_FIX_WORKSPACE_ROOT", "").strip()
    if configured_root:
        return Path(configured_root).resolve()
    return Path(__file__).resolve().parents[2] / ".local" / "auto-fix-workspaces"


def configured() -> bool:
    gitlab = get_settings()
    return bool(
        (os.getenv("AUTO_FIX_GITLAB_POLICY_VERIFIED", "").strip().lower() or "true") == "true"
        and gitlab.gitlab_api_enabled and gitlab.gitlab_base_url and gitlab.gitlab_token
    )
