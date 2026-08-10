from __future__ import annotations

from datetime import datetime, timedelta
import json

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent_review import repository as agent_repository
from app.agent_review.models import (
    AgentReviewRun,
    AgentReviewRuntime,
    AgentReviewSettings,
    AgentReviewWorker,
)
from app.agent_review.runtime import CUSTOM_RUNTIME, DEFAULT_RUNTIME
from app.core.json_utils import utc_now


def _configure_worker(
    client: TestClient,
    monkeypatch,
    capabilities: list[str] | None = None,
) -> None:
    monkeypatch.setenv(
        "AGENT_REVIEW_CONFIG_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    monkeypatch.setenv("AGENT_REVIEW_WORKER_TOKEN", "runtime-worker-token")
    response = client.post(
        "/internal/agent-review/workers/heartbeat",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={
            "workerId": "runtime-worker",
            "workerVersion": "test",
            "cliVersion": "test",
            "capabilities": capabilities or [DEFAULT_RUNTIME, CUSTOM_RUNTIME],
            "responsesRunnerVersion": "openai-responses-agent-v1",
        },
    )
    assert response.status_code == 200


def _runtime_payload(runtime_code: str = "RELAY_A") -> dict:
    return {
        "runtimeCode": runtime_code,
        "displayName": "Relay A",
        "protocol": "OPENAI_RESPONSES",
        "baseUrl": "https://relay.example.com/v1/",
        "model": "gpt-5.6-sol",
        "reasoningEffort": "high",
        "tlsVerify": True,
        "apiKey": "runtime-secret",
    }


def _chat_runtime_payload(runtime_code: str = "CHAT_AGENT") -> dict:
    payload = {
        **_runtime_payload(runtime_code),
        "displayName": "Chat Agent",
        "protocol": "OPENAI_CHAT_COMPLETIONS",
        "model": "chat-model",
    }
    payload.pop("reasoningEffort")
    return payload


def _anthropic_runtime_payload(runtime_code: str = "ANTHROPIC_AGENT") -> dict:
    payload = {
        **_runtime_payload(runtime_code),
        "displayName": "Anthropic Agent",
        "protocol": "ANTHROPIC_MESSAGES",
        "model": "claude-sonnet",
    }
    payload.pop("reasoningEffort")
    return payload


def test_anthropic_runtime_contract_capability_snapshot_claim_fallback_and_history(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(
        client,
        monkeypatch,
        [DEFAULT_RUNTIME, CUSTOM_RUNTIME, "ANTHROPIC_MESSAGES_AGENT"],
    )
    created = client.post(
        "/api/code-quality-agent-runtimes",
        json=_anthropic_runtime_payload(),
    )
    assert created.status_code == 200
    assert created.json()["data"]["runnerType"] == "ANTHROPIC_MESSAGES_AGENT"
    assert client.put(
        "/api/code-quality-agent-runtimes/ANTHROPIC_AGENT",
        json={"enabled": True},
    ).status_code == 200

    requested = client.post(
        "/api/code-quality-agent-runtimes/ANTHROPIC_AGENT/test"
    )
    assert requested.status_code == 200
    claimed_test = client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={"workerId": "runtime-worker"},
    ).json()["data"]
    assert claimed_test["runtime"]["runnerType"] == "ANTHROPIC_MESSAGES_AGENT"
    assert claimed_test["runtime"]["reasoningEffort"] is None
    assert claimed_test["runtime"]["apiKey"] == "runtime-secret"
    assert client.post(
        "/internal/agent-review/configuration-test/complete",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={
            "workerId": "runtime-worker",
            "requestId": claimed_test["requestId"],
            "status": "SUCCESS",
            "message": "synthetic anthropic success",
            "durationMs": 10,
        },
    ).status_code == 200

    assert client.post(
        "/api/code-quality-agent-runtimes/ANTHROPIC_AGENT/set-current"
    ).status_code == 200
    snapshot = agent_repository.selected_agent_runtime_snapshot(db_session)
    assert snapshot["protocol"] == "ANTHROPIC_MESSAGES"
    assert snapshot["runnerType"] == "ANTHROPIC_MESSAGES_AGENT"
    assert snapshot["reasoningEffort"] is None
    run = agent_repository.create_agent_job(
        db_session,
        task_id=905,
        project_id=100,
        input_payload={
            "worktree": "worktrees/905/head",
            "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=False,
        runtime=snapshot,
    )
    db_session.commit()
    assert run.runner_version == "anthropic-messages-agent-v1"
    assert run.review_key == "agent-runtime-anthropic-agent"
    assert "runtime-secret" not in run.input_json
    history = agent_repository.run_to_summary(run)
    assert history["runnerType"] == "ANTHROPIC_MESSAGES_AGENT"
    assert history["runnerVersion"] == "anthropic-messages-agent-v1"
    assert history["model"] == "claude-sonnet"

    claimed = client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={"workerId": "runtime-worker"},
    ).json()["data"]
    assert claimed["runtime"]["runnerType"] == "ANTHROPIC_MESSAGES_AGENT"
    assert claimed["runtime"]["apiKey"] == "runtime-secret"

    fallback_run = agent_repository.create_agent_job(
        db_session,
        task_id=906,
        project_id=100,
        input_payload={
            "worktree": "worktrees/906/head",
            "case": {"changedFiles": ["src/b.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=False,
        runtime=snapshot,
    )
    db_session.commit()
    assert client.put(
        "/api/code-quality-agent-runtimes/ANTHROPIC_AGENT",
        json={"clearApiKey": True},
    ).status_code == 200
    fallback_ids: list[int] = []
    monkeypatch.setattr(
        "app.code_quality.service.schedule_agent_standard_fallback",
        lambda _db, run_id: fallback_ids.append(run_id),
    )
    assert client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={"workerId": "runtime-worker"},
    ).json()["data"] is None
    assert fallback_ids == [fallback_run.id]


def test_runtime_catalog_seeds_legacy_records_and_never_returns_ciphertext(
    client: TestClient,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch)

    response = client.get("/api/code-quality-agent-runtimes")

    assert response.status_code == 200
    data = response.json()["data"]
    assert [item["runtimeCode"] for item in data] == [DEFAULT_RUNTIME, CUSTOM_RUNTIME]
    assert data[0]["selected"] is True
    assert data[0]["protocolAvailable"] is True
    assert data[1]["protocolAvailable"] is True
    assert data[1]["configurationTest"]["status"] == "NOT_RUN"
    assert "ciphertext" not in response.text.casefold()
    assert "runtime-secret" not in response.text


def test_runtime_create_requires_open_protocol_and_online_runner(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "AGENT_REVIEW_CONFIG_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    no_worker = client.post(
        "/api/code-quality-agent-runtimes",
        json=_runtime_payload(),
    )
    assert no_worker.status_code == 409
    assert no_worker.json()["code"] == "AGENT_RUNTIME_RUNNER_UNAVAILABLE"

    _configure_worker(client, monkeypatch)
    chat_payload = {
        **_runtime_payload("CHAT_AGENT"),
        "protocol": "OPENAI_CHAT_COMPLETIONS",
    }
    chat_payload.pop("reasoningEffort")
    unavailable = client.post(
        "/api/code-quality-agent-runtimes",
        json=chat_payload,
    )
    assert unavailable.status_code == 409
    assert unavailable.json()["code"] == "AGENT_RUNTIME_RUNNER_UNAVAILABLE"


def test_runtime_create_derives_runner_and_does_not_enable_select_or_test(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch)

    response = client.post(
        "/api/code-quality-agent-runtimes",
        json=_runtime_payload("relay_a"),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["runtimeCode"] == "RELAY_A"
    assert data["runnerType"] == "OPENAI_RESPONSES_AGENT"
    assert data["baseUrl"] == "https://relay.example.com/v1"
    assert data["enabled"] is False
    assert data["selected"] is False
    assert data["configurationTest"]["status"] == "NOT_RUN"
    assert data["apiKeyConfigured"] is True
    assert "runtime-secret" not in response.text
    runtime = db_session.get(AgentReviewRuntime, "RELAY_A")
    assert runtime is not None
    assert runtime.api_key_ciphertext != "runtime-secret"

    duplicate = client.post(
        "/api/code-quality-agent-runtimes",
        json=_runtime_payload("RELAY_A"),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "AGENT_RUNTIME_ALREADY_EXISTS"

    forbidden_runner = client.post(
        "/api/code-quality-agent-runtimes",
        json={**_runtime_payload("RELAY_B"), "runnerType": "CLAUDE_CODE"},
    )
    assert forbidden_runner.status_code == 400
    assert forbidden_runner.json()["code"] == "VALIDATION_ERROR"

    invalid_code = client.post(
        "/api/code-quality-agent-runtimes",
        json=_runtime_payload("BAD-CODE"),
    )
    assert invalid_code.status_code == 400
    assert invalid_code.json()["code"] == "VALIDATION_ERROR"

    unsafe_url = client.post(
        "/api/code-quality-agent-runtimes",
        json={**_runtime_payload("UNSAFE_URL"), "baseUrl": "http://127.0.0.1/v1"},
    )
    assert unsafe_url.status_code == 400
    assert unsafe_url.json()["code"] == "VALIDATION_ERROR"


def test_runtime_update_preserves_rotates_and_explicitly_clears_key(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch)
    assert client.post(
        "/api/code-quality-agent-runtimes",
        json=_runtime_payload(),
    ).status_code == 200
    original = db_session.get(AgentReviewRuntime, "RELAY_A").api_key_ciphertext

    kept = client.put(
        "/api/code-quality-agent-runtimes/relay_a",
        json={"displayName": "Relay renamed", "apiKey": None},
    )
    assert kept.status_code == 200
    db_session.expire_all()
    assert db_session.get(AgentReviewRuntime, "RELAY_A").api_key_ciphertext == original

    rotated = client.put(
        "/api/code-quality-agent-runtimes/RELAY_A",
        json={"apiKey": "rotated-secret", "enabled": True},
    )
    assert rotated.status_code == 200
    assert rotated.json()["data"]["enabled"] is True
    db_session.expire_all()
    assert db_session.get(AgentReviewRuntime, "RELAY_A").api_key_ciphertext != original

    cleared = client.put(
        "/api/code-quality-agent-runtimes/RELAY_A",
        json={"clearApiKey": True},
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["enabled"] is False
    assert cleared.json()["data"]["apiKeyConfigured"] is False

    immutable = client.put(
        f"/api/code-quality-agent-runtimes/{DEFAULT_RUNTIME}",
        json={"model": "replacement"},
    )
    assert immutable.status_code == 409
    assert immutable.json()["code"] == "AGENT_RUNTIME_BUILT_IN_IMMUTABLE"

    invalid_null = client.put(
        "/api/code-quality-agent-runtimes/RELAY_A",
        json={"displayName": None},
    )
    assert invalid_null.status_code == 400
    assert invalid_null.json()["code"] == "VALIDATION_ERROR"


def test_historical_custom_runtime_updates_dual_write_legacy_slot(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch)

    updated = client.put(
        f"/api/code-quality-agent-runtimes/{CUSTOM_RUNTIME}",
        json={
            "displayName": "Legacy relay updated",
            "baseUrl": "https://legacy-relay.example.com/v1",
            "model": "gpt-5.6-sol",
            "reasoningEffort": "medium",
            "tlsVerify": False,
            "apiKey": "legacy-runtime-rotated",
            "enabled": True,
        },
    )

    assert updated.status_code == 200
    settings = db_session.get(AgentReviewSettings, 1)
    runtime = db_session.get(AgentReviewRuntime, CUSTOM_RUNTIME)
    assert settings.custom_display_name == "Legacy relay updated"
    assert settings.custom_base_url == "https://legacy-relay.example.com/v1"
    assert settings.custom_reasoning_effort == "medium"
    assert settings.custom_tls_verify is False
    assert settings.custom_api_key_ciphertext == runtime.api_key_ciphertext
    assert "legacy-runtime-rotated" not in updated.text

    assert client.post(
        f"/api/code-quality-agent-runtimes/{CUSTOM_RUNTIME}/set-current"
    ).status_code == 200
    assert client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True},
    ).status_code == 200
    disabled = client.put(
        f"/api/code-quality-agent-runtimes/{CUSTOM_RUNTIME}",
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    db_session.expire_all()
    assert db_session.get(AgentReviewSettings, 1).enabled is False


def test_set_current_requires_enabled_complete_runtime_and_projects_legacy_type(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch)
    assert client.post(
        "/api/code-quality-agent-runtimes",
        json=_runtime_payload("DYNAMIC_RESPONSES"),
    ).status_code == 200

    disabled = client.post(
        "/api/code-quality-agent-runtimes/DYNAMIC_RESPONSES/set-current"
    )
    assert disabled.status_code == 409
    assert disabled.json()["code"] == "AGENT_RUNTIME_DISABLED"
    assert client.put(
        "/api/code-quality-agent-runtimes/DYNAMIC_RESPONSES",
        json={"enabled": True},
    ).status_code == 200

    selected = client.post(
        "/api/code-quality-agent-runtimes/DYNAMIC_RESPONSES/set-current"
    )

    assert selected.status_code == 200
    assert selected.json()["data"]["selectedRuntimeCode"] == "DYNAMIC_RESPONSES"
    settings = db_session.get(AgentReviewSettings, 1)
    assert settings.selected_runtime_code == "DYNAMIC_RESPONSES"
    assert settings.runtime_type == DEFAULT_RUNTIME
    assert settings.enabled is False
    compatible_update = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": False},
    )
    assert compatible_update.status_code == 200
    db_session.expire_all()
    assert (
        db_session.get(AgentReviewSettings, 1).selected_runtime_code
        == "DYNAMIC_RESPONSES"
    )
    available_execution = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True},
    )
    assert available_execution.status_code == 200
    current = client.delete(
        "/api/code-quality-agent-runtimes/DYNAMIC_RESPONSES"
    )
    assert current.status_code == 409
    assert current.json()["code"] == "AGENT_RUNTIME_IS_CURRENT"


def test_dynamic_responses_snapshot_review_key_and_claim_use_current_key(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch)
    runtime_code = "TEAM_RELAY"
    assert client.post(
        "/api/code-quality-agent-runtimes",
        json=_runtime_payload(runtime_code),
    ).status_code == 200
    assert client.put(
        f"/api/code-quality-agent-runtimes/{runtime_code}",
        json={"enabled": True},
    ).status_code == 200
    assert client.post(
        f"/api/code-quality-agent-runtimes/{runtime_code}/set-current"
    ).status_code == 200
    assert client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True},
    ).status_code == 200

    snapshot = agent_repository.selected_agent_runtime_snapshot(db_session)
    run = agent_repository.create_agent_job(
        db_session,
        task_id=901,
        project_id=100,
        input_payload={
            "worktree": "worktrees/901/head",
            "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=False,
        runtime=snapshot,
    )
    db_session.commit()

    assert run.review_key == "agent-runtime-team-relay"
    assert run.runner_type == "OPENAI_RESPONSES_AGENT"
    persisted_input = json.loads(run.input_json)
    assert persisted_input["runtimeSnapshot"] == {
        "runtimeCode": runtime_code,
        "runtimeType": runtime_code,
        "protocol": "OPENAI_RESPONSES",
        "wireProtocol": "OPENAI_RESPONSES",
        "runnerType": "OPENAI_RESPONSES_AGENT",
        "displayName": "Relay A",
        "baseUrl": "https://relay.example.com/v1",
        "model": "gpt-5.6-sol",
        "reasoningEffort": "high",
        "tlsVerify": True,
        "credentialSlot": f"AGENT_RUNTIME:{runtime_code}",
    }
    assert "runtime-secret" not in run.input_json

    assert client.put(
        f"/api/code-quality-agent-runtimes/{runtime_code}",
        json={"apiKey": "rotated-runtime-secret"},
    ).status_code == 200
    claimed = client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={"workerId": "runtime-worker"},
    )

    assert claimed.status_code == 200
    job = claimed.json()["data"]
    assert job["runId"] == run.id
    assert job["reviewKey"] == "agent-runtime-team-relay"
    assert job["runtime"]["runtimeCode"] == runtime_code
    assert job["runtime"]["runnerType"] == "OPENAI_RESPONSES_AGENT"
    assert job["runtime"]["apiKey"] == "rotated-runtime-secret"
    assert "rotated-runtime-secret" not in run.input_json


def test_chat_runtime_configuration_snapshot_and_claim_use_chat_capability(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(
        client,
        monkeypatch,
        [DEFAULT_RUNTIME, CUSTOM_RUNTIME, "OPENAI_CHAT_AGENT"],
    )
    created = client.post(
        "/api/code-quality-agent-runtimes",
        json=_chat_runtime_payload(),
    )
    assert created.status_code == 200
    created_data = created.json()["data"]
    assert created_data["runnerType"] == "OPENAI_CHAT_AGENT"
    assert created_data["protocolAvailable"] is True
    assert created_data["reasoningEffort"] is None
    assert client.put(
        "/api/code-quality-agent-runtimes/CHAT_AGENT",
        json={"enabled": True},
    ).status_code == 200

    requested_test = client.post(
        "/api/code-quality-agent-runtimes/CHAT_AGENT/test"
    )
    assert requested_test.status_code == 200
    claimed_test = client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={"workerId": "runtime-worker"},
    ).json()["data"]
    assert claimed_test["kind"] == "CONFIG_TEST"
    assert claimed_test["runtime"]["runnerType"] == "OPENAI_CHAT_AGENT"
    assert claimed_test["runtime"]["reasoningEffort"] is None
    assert claimed_test["runtime"]["apiKey"] == "runtime-secret"
    completed_test = client.post(
        "/internal/agent-review/configuration-test/complete",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={
            "workerId": "runtime-worker",
            "requestId": claimed_test["requestId"],
            "status": "SUCCESS",
            "message": "synthetic chat success",
            "durationMs": 12,
        },
    )
    assert completed_test.status_code == 200

    assert client.post(
        "/api/code-quality-agent-runtimes/CHAT_AGENT/set-current"
    ).status_code == 200
    assert client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True},
    ).status_code == 200
    snapshot = agent_repository.selected_agent_runtime_snapshot(db_session)
    assert snapshot == {
        "runtimeCode": "CHAT_AGENT",
        "runtimeType": "CHAT_AGENT",
        "protocol": "OPENAI_CHAT_COMPLETIONS",
        "wireProtocol": "OPENAI_CHAT_COMPLETIONS",
        "runnerType": "OPENAI_CHAT_AGENT",
        "displayName": "Chat Agent",
        "baseUrl": "https://relay.example.com/v1",
        "model": "chat-model",
        "reasoningEffort": None,
        "tlsVerify": True,
        "credentialSlot": "AGENT_RUNTIME:CHAT_AGENT",
    }
    run = agent_repository.create_agent_job(
        db_session,
        task_id=903,
        project_id=100,
        input_payload={
            "worktree": "worktrees/903/head",
            "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=False,
        runtime=snapshot,
    )
    db_session.commit()
    assert run.runner_type == "OPENAI_CHAT_AGENT"
    assert run.runner_version == "openai-chat-completions-agent-v1"
    assert run.review_key == "agent-runtime-chat-agent"
    assert "runtime-secret" not in run.input_json

    claimed = client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={"workerId": "runtime-worker"},
    ).json()["data"]
    assert claimed["runId"] == run.id
    assert claimed["runtime"]["runnerType"] == "OPENAI_CHAT_AGENT"
    assert claimed["runtime"]["apiKey"] == "runtime-secret"

    fallback_run = agent_repository.create_agent_job(
        db_session,
        task_id=904,
        project_id=100,
        input_payload={
            "worktree": "worktrees/904/head",
            "case": {"changedFiles": ["src/b.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=False,
        runtime=snapshot,
    )
    db_session.commit()
    assert client.put(
        "/api/code-quality-agent-runtimes/CHAT_AGENT",
        json={"clearApiKey": True},
    ).status_code == 200
    fallback_ids: list[int] = []
    monkeypatch.setattr(
        "app.code_quality.service.schedule_agent_standard_fallback",
        lambda _db, run_id: fallback_ids.append(run_id),
    )
    unavailable_claim = client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={"workerId": "runtime-worker"},
    )
    assert unavailable_claim.status_code == 200
    assert unavailable_claim.json()["data"] is None
    assert fallback_ids == [fallback_run.id]
    db_session.expire_all()
    assert db_session.get(AgentReviewRun, fallback_run.id).failure_code == (
        "AGENT_RUNTIME_DISABLED"
    )


def test_queued_dynamic_runtime_with_cleared_key_fails_and_schedules_fallback(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch)
    runtime_code = "FALLBACK_RELAY"
    assert client.post(
        "/api/code-quality-agent-runtimes",
        json=_runtime_payload(runtime_code),
    ).status_code == 200
    assert client.put(
        f"/api/code-quality-agent-runtimes/{runtime_code}",
        json={"enabled": True},
    ).status_code == 200
    assert client.post(
        f"/api/code-quality-agent-runtimes/{runtime_code}/set-current"
    ).status_code == 200
    assert client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True},
    ).status_code == 200
    run = agent_repository.create_agent_job(
        db_session,
        task_id=902,
        project_id=100,
        input_payload={
            "worktree": "worktrees/902/head",
            "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=False,
        runtime=agent_repository.selected_agent_runtime_snapshot(db_session),
    )
    db_session.commit()
    assert client.put(
        f"/api/code-quality-agent-runtimes/{runtime_code}",
        json={"clearApiKey": True},
    ).status_code == 200
    fallback_run_ids: list[int] = []
    monkeypatch.setattr(
        "app.code_quality.service.schedule_agent_standard_fallback",
        lambda _db, run_id: fallback_run_ids.append(run_id),
    )

    claimed = client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={"workerId": "runtime-worker"},
    )

    assert claimed.status_code == 200
    assert claimed.json()["data"] is None
    assert fallback_run_ids == [run.id]
    db_session.expire_all()
    failed = db_session.get(AgentReviewRun, run.id)
    assert failed.status == "FAILED"
    assert failed.effective_engine == "STANDARD_FALLBACK"
    assert failed.failure_code == "AGENT_RUNTIME_DISABLED"


def test_non_current_runtime_configuration_test_claim_and_callback_contract(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch)
    runtime_code = "TEST_RELAY"
    assert client.post(
        "/api/code-quality-agent-runtimes",
        json=_runtime_payload(runtime_code),
    ).status_code == 200
    assert client.put(
        f"/api/code-quality-agent-runtimes/{runtime_code}",
        json={"enabled": True},
    ).status_code == 200
    assert db_session.get(AgentReviewSettings, 1).selected_runtime_code == DEFAULT_RUNTIME
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={
            "workerId": "default-only-worker",
            "capabilities": [DEFAULT_RUNTIME],
        },
    )

    requested = client.post(
        f"/api/code-quality-agent-runtimes/{runtime_code}/test"
    )

    assert requested.status_code == 200
    test_state = requested.json()["data"]
    assert test_state["runtimeCode"] == runtime_code
    assert test_state["status"] == "QUEUED"
    assert test_state["runnerType"] == "OPENAI_RESPONSES_AGENT"
    duplicate = client.post(
        f"/api/code-quality-agent-runtimes/{runtime_code}/test"
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "AGENT_RUNTIME_TEST_ACTIVE"
    unsupported_claim = client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={"workerId": "default-only-worker"},
    )
    assert unsupported_claim.status_code == 200
    assert unsupported_claim.json()["data"] is None

    claimed = client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={"workerId": "runtime-worker"},
    )
    job = claimed.json()["data"]
    assert job["kind"] == "CONFIG_TEST"
    assert job["requestId"] == test_state["requestId"]
    assert job["runtime"]["runtimeCode"] == runtime_code
    assert job["runtime"]["runnerType"] == "OPENAI_RESPONSES_AGENT"
    assert job["runtime"]["apiKey"] == "runtime-secret"

    completed = client.post(
        "/internal/agent-review/configuration-test/complete",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={
            "workerId": "runtime-worker",
            "requestId": job["requestId"],
            "status": "SUCCESS",
            "message": "synthetic review completed",
            "durationMs": 123,
        },
    )
    assert completed.status_code == 200
    assert completed.json()["data"]["status"] == "SUCCESS"
    assert completed.json()["data"]["durationMs"] == 123
    idempotent = client.post(
        "/internal/agent-review/configuration-test/complete",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={
            "workerId": "runtime-worker",
            "requestId": job["requestId"],
            "status": "FAILED",
            "message": "must not overwrite",
        },
    )
    assert idempotent.status_code == 200
    assert idempotent.json()["data"]["status"] == "SUCCESS"
    catalog = client.get("/api/code-quality-agent-runtimes").json()["data"]
    runtime_item = next(item for item in catalog if item["runtimeCode"] == runtime_code)
    assert runtime_item["configurationTest"]["status"] == "SUCCESS"
    assert "runtime-secret" not in str(runtime_item)


def test_runtime_configuration_test_timeout_stale_callback_and_worker_gate(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch)
    runtime_code = "TIMEOUT_RELAY"
    assert client.post(
        "/api/code-quality-agent-runtimes",
        json=_runtime_payload(runtime_code),
    ).status_code == 200
    assert client.put(
        f"/api/code-quality-agent-runtimes/{runtime_code}",
        json={"enabled": True},
    ).status_code == 200
    first = client.post(
        f"/api/code-quality-agent-runtimes/{runtime_code}/test"
    ).json()["data"]
    runtime = db_session.get(AgentReviewRuntime, runtime_code)
    runtime.test_status = "RUNNING"
    runtime.test_started_at = utc_now() - timedelta(seconds=91)
    db_session.commit()

    catalog = client.get("/api/code-quality-agent-runtimes").json()["data"]
    timed_out = next(item for item in catalog if item["runtimeCode"] == runtime_code)
    assert timed_out["configurationTest"]["status"] == "FAILED"
    assert timed_out["configurationTest"]["message"] == (
        "Agent Runtime configuration test timed out"
    )
    second = client.post(
        f"/api/code-quality-agent-runtimes/{runtime_code}/test"
    )
    assert second.status_code == 200
    assert second.json()["data"]["requestId"] != first["requestId"]
    stale = client.post(
        "/internal/agent-review/configuration-test/complete",
        headers={"X-Agent-Worker-Token": "runtime-worker-token"},
        json={
            "workerId": "runtime-worker",
            "requestId": first["requestId"],
            "status": "SUCCESS",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "AGENT_CONFIG_TEST_STALE"

    assert client.put(
        f"/api/code-quality-agent-runtimes/{runtime_code}",
        json={"enabled": False},
    ).status_code == 200
    db_session.expire_all()
    runtime = db_session.get(AgentReviewRuntime, runtime_code)
    assert runtime.test_status == "FAILED"
    assert "disabled" in runtime.test_message
    disabled = client.post(
        f"/api/code-quality-agent-runtimes/{runtime_code}/test"
    )
    assert disabled.status_code == 409
    assert disabled.json()["code"] == "AGENT_RUNTIME_DISABLED"

    runtime.enabled = True
    capable_worker = db_session.get(AgentReviewWorker, "runtime-worker")
    capable_worker.last_heartbeat_at = utc_now() - timedelta(seconds=61)
    db_session.commit()
    unavailable = client.post(
        f"/api/code-quality-agent-runtimes/{runtime_code}/test"
    )
    assert unavailable.status_code == 409
    assert unavailable.json()["code"] == "AGENT_RUNTIME_RUNNER_UNAVAILABLE"


def test_configuration_tests_queue_independently_per_runtime(
    client: TestClient,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch)
    runtime_codes = {"QUEUE_RELAY_A", "QUEUE_RELAY_B"}
    request_ids = set()
    for runtime_code in sorted(runtime_codes):
        assert client.post(
            "/api/code-quality-agent-runtimes",
            json=_runtime_payload(runtime_code),
        ).status_code == 200
        assert client.put(
            f"/api/code-quality-agent-runtimes/{runtime_code}",
            json={"enabled": True},
        ).status_code == 200
        requested = client.post(
            f"/api/code-quality-agent-runtimes/{runtime_code}/test"
        )
        assert requested.status_code == 200
        request_ids.add(requested.json()["data"]["requestId"])

    claimed = {
        client.post(
            "/internal/agent-review/jobs/claim",
            headers={"X-Agent-Worker-Token": "runtime-worker-token"},
            json={"workerId": "runtime-worker"},
        ).json()["data"]["requestId"]
        for _ in runtime_codes
    }

    assert claimed == request_ids


def test_delete_protects_built_in_current_active_test_and_active_task(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch)
    built_in = client.delete(f"/api/code-quality-agent-runtimes/{DEFAULT_RUNTIME}")
    assert built_in.status_code == 409
    assert built_in.json()["code"] == "AGENT_RUNTIME_BUILT_IN"

    assert client.post(
        "/api/code-quality-agent-runtimes",
        json=_runtime_payload("DELETE_GUARD"),
    ).status_code == 200
    runtime = db_session.get(AgentReviewRuntime, "DELETE_GUARD")
    runtime.test_status = "QUEUED"
    db_session.commit()
    active_test = client.delete("/api/code-quality-agent-runtimes/DELETE_GUARD")
    assert active_test.status_code == 409
    assert active_test.json()["code"] == "AGENT_RUNTIME_TEST_ACTIVE"

    runtime.test_status = "SUCCESS"
    run = AgentReviewRun(
        task_id=9901,
        review_key="agent-runtime-delete-guard",
        idempotency_key="runtime-delete-guard",
        runner_type="OPENAI_RESPONSES_AGENT",
        provider="CUSTOM_OPENAI",
        model="gpt-5.6-sol",
        status="PENDING",
        input_json=json.dumps(
            {"runtimeSnapshot": {"runtimeCode": "DELETE_GUARD"}}
        ),
        created_at=datetime(2026, 8, 10, 12, 0, 0),
        updated_at=datetime(2026, 8, 10, 12, 0, 0),
    )
    db_session.add(run)
    db_session.commit()
    active_task = client.delete("/api/code-quality-agent-runtimes/DELETE_GUARD")
    assert active_task.status_code == 409
    assert active_task.json()["code"] == "AGENT_RUNTIME_IN_USE"

    run.status = "SUCCESS"
    db_session.commit()
    deleted = client.delete("/api/code-quality-agent-runtimes/DELETE_GUARD")
    assert deleted.status_code == 200
    assert deleted.json()["data"] == {
        "runtimeCode": "DELETE_GUARD",
        "deleted": True,
    }
    assert db_session.get(AgentReviewRun, run.id) is not None
    repeated = client.delete("/api/code-quality-agent-runtimes/DELETE_GUARD")
    assert repeated.status_code == 404


def test_delete_legacy_custom_runtime_does_not_recreate_empty_slot(
    client: TestClient,
    db_session: Session,
) -> None:
    settings = client.get("/api/code-quality-reviews/agent-settings")
    assert settings.status_code == 200
    record = db_session.get(AgentReviewSettings, 1)
    record.selected_runtime_code = DEFAULT_RUNTIME
    record.runtime_type = DEFAULT_RUNTIME
    db_session.commit()

    deleted = client.delete(f"/api/code-quality-agent-runtimes/{CUSTOM_RUNTIME}")

    assert deleted.status_code == 200
    catalog = client.get("/api/code-quality-agent-runtimes").json()["data"]
    assert [item["runtimeCode"] for item in catalog] == [DEFAULT_RUNTIME]
