from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.agent_review.models import AgentReviewRuntime, AgentReviewSettings
from app.agent_review.repository import (
    _supports_skip_locked,
    _ensure_settings_columns,
    agent_runtime_record_response,
    ensure_legacy_agent_runtime_records,
    get_agent_settings_record,
    list_agent_runtime_records,
    sync_legacy_agent_runtime_records,
)
from app.agent_review.runtime import CUSTOM_RUNTIME, DEFAULT_RUNTIME


class _Session:
    def __init__(
        self,
        *,
        dialect_name: str,
        version: tuple[object, ...] | None,
        is_mariadb: bool = False,
    ) -> None:
        dialect = SimpleNamespace(
            name=dialect_name,
            server_version_info=version,
            is_mariadb=is_mariadb,
        )
        self._bind = SimpleNamespace(dialect=dialect)

    def get_bind(self):
        return self._bind


@pytest.mark.parametrize(
    ("session", "expected"),
    [
        (_Session(dialect_name="mysql", version=(5, 7, 31)), False),
        (_Session(dialect_name="mysql", version=(8, 0, 0)), True),
        (_Session(dialect_name="mysql", version=(8, 4, 1)), True),
        (_Session(dialect_name="mysql", version=(10, 6, 0), is_mariadb=True), False),
        (_Session(dialect_name="sqlite", version=(3, 45, 0)), False),
        (_Session(dialect_name="mysql", version=None), False),
        (_Session(dialect_name="mysql", version=("unknown",)), False),
    ],
)
def test_skip_locked_support_is_enabled_only_for_mysql_8_or_newer(session: _Session, expected: bool) -> None:
    assert _supports_skip_locked(session) is expected


def test_empty_database_seeds_two_legacy_runtimes(db_session: Session) -> None:
    settings = get_agent_settings_record(db_session)
    runtimes = list_agent_runtime_records(db_session)

    assert settings.selected_runtime_code == DEFAULT_RUNTIME
    assert [runtime.runtime_code for runtime in runtimes] == [
        DEFAULT_RUNTIME,
        CUSTOM_RUNTIME,
    ]
    assert runtimes[0].built_in is True
    assert runtimes[0].runner_type == "CLAUDE_CODE"
    assert runtimes[1].built_in is False
    assert runtimes[1].runner_type == "OPENAI_RESPONSES_AGENT"


def test_legacy_custom_runtime_migrates_ciphertext_selection_and_test_state(
    db_session: Session,
) -> None:
    settings = AgentReviewSettings(
        id=1,
        enabled=True,
        runtime_type=CUSTOM_RUNTIME,
        selected_runtime_code=CUSTOM_RUNTIME,
        api_key_ciphertext="default-ciphertext",
        api_key_fingerprint="default-fingerprint",
        custom_display_name="Relay A",
        custom_base_url="https://relay.example.com/v1",
        custom_model="gpt-5.6-sol",
        custom_reasoning_effort="high",
        custom_tls_verify=False,
        custom_api_key_ciphertext="custom-ciphertext",
        custom_api_key_fingerprint="custom-fingerprint",
        test_request_id="request-custom",
        test_status="SUCCESS",
    )
    db_session.add(settings)
    db_session.flush()

    default_runtime, custom_runtime = ensure_legacy_agent_runtime_records(
        db_session, settings
    )

    assert default_runtime.api_key_ciphertext == "default-ciphertext"
    assert default_runtime.test_status is None
    assert custom_runtime.api_key_ciphertext == "custom-ciphertext"
    assert custom_runtime.api_key_fingerprint == "custom-fingerprint"
    assert custom_runtime.tls_verify is False
    assert custom_runtime.test_request_id == "request-custom"
    assert custom_runtime.test_status == "SUCCESS"


def test_invalid_selection_falls_back_without_overwriting_existing_runtime(
    db_session: Session,
) -> None:
    settings = AgentReviewSettings(
        id=1,
        enabled=False,
        runtime_type="REMOVED_RUNTIME",
        selected_runtime_code="REMOVED_RUNTIME",
    )
    existing = AgentReviewRuntime(
        runtime_code=CUSTOM_RUNTIME,
        display_name="Existing target",
        protocol="OPENAI_RESPONSES",
        runner_type="OPENAI_RESPONSES_AGENT",
        model_name="existing-model",
        tls_verify=True,
        enabled=False,
        built_in=False,
        sort_order=99,
    )
    db_session.add_all([settings, existing])
    db_session.flush()

    _default_runtime, custom_runtime = ensure_legacy_agent_runtime_records(
        db_session, settings
    )

    assert settings.selected_runtime_code == DEFAULT_RUNTIME
    assert settings.runtime_type == DEFAULT_RUNTIME
    assert custom_runtime.display_name == "Existing target"
    assert custom_runtime.model_name == "existing-model"
    assert custom_runtime.sort_order == 99


def test_legacy_dual_write_preserves_ciphertext_and_masks_runtime_response(
    db_session: Session,
) -> None:
    settings = get_agent_settings_record(db_session)
    settings.custom_display_name = "Updated relay"
    settings.custom_api_key_ciphertext = "opaque-ciphertext"
    settings.custom_api_key_fingerprint = "1234567890abcdef"
    settings.selected_runtime_code = CUSTOM_RUNTIME
    settings.runtime_type = CUSTOM_RUNTIME

    _default_runtime, custom_runtime = sync_legacy_agent_runtime_records(
        db_session, settings
    )
    response = agent_runtime_record_response(custom_runtime)

    assert custom_runtime.api_key_ciphertext == "opaque-ciphertext"
    assert response["displayName"] == "Updated relay"
    assert response["apiKeyConfigured"] is True
    assert response["apiKeyMasked"].startswith("configured:")
    assert "ciphertext" not in str(response)


def test_legacy_schema_backfills_selected_runtime_from_old_runtime_type() -> None:
    existing_columns = {
        "runtime_type",
        "custom_display_name",
        "custom_base_url",
        "custom_model",
        "custom_reasoning_effort",
        "custom_tls_verify",
        "custom_api_key_ciphertext",
        "custom_api_key_fingerprint",
        "budget_config_json",
        "test_request_id",
        "test_status",
        "test_message",
        "test_duration_ms",
        "test_started_at",
        "test_finished_at",
    }

    class Inspector:
        @staticmethod
        def get_columns(_table_name):
            return [{"name": name} for name in existing_columns]

    class SessionStub:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement):
            self.statements.append(str(statement))

        @staticmethod
        def flush() -> None:
            return None

    session = SessionStub()

    _ensure_settings_columns(session, Inspector())  # type: ignore[arg-type]

    assert any(
        "ADD COLUMN selected_runtime_code" in statement
        for statement in session.statements
    )
    assert any(
        "WHEN runtime_type = 'OPENAI_RESPONSES_CUSTOM'" in statement
        for statement in session.statements
    )
