import json

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_review import repository as agent_repository
from app.agent_review.models import AgentReviewRuntime, AgentReviewSettings
from app.agent_review.runtime import DEFAULT_RUNTIME
from app.code_quality import providers
from app.code_quality.models import CodeQualityModelProvider, CodeQualityReviewSettings


def _configure_worker(
    client: TestClient,
    monkeypatch,
    capabilities: list[str],
) -> None:
    monkeypatch.setenv(
        "AGENT_REVIEW_CONFIG_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    monkeypatch.setenv("AGENT_REVIEW_WORKER_TOKEN", "connection-worker-token")
    response = client.post(
        "/internal/agent-review/workers/heartbeat",
        headers={"X-Agent-Worker-Token": "connection-worker-token"},
        json={
            "workerId": "connection-worker",
            "workerVersion": "test",
            "cliVersion": "test",
            "capabilities": capabilities,
        },
    )
    assert response.status_code == 200


def _connection_payload(
    *,
    preset_code: str = "AGENT_CLAUDE_CODE_DEEPSEEK",
    protocol: str = "ANTHROPIC_COMPATIBLE",
    base_url: str = "https://api.deepseek.com/anthropic",
    model: str = "deepseek-v4-pro[1m]",
    api_key: str = "deepseek-runtime-secret",
) -> dict:
    payload = {
        "reviewType": "AGENT",
        "presetCode": preset_code,
        "protocol": protocol,
        "baseUrl": base_url,
        "model": model,
        "apiKey": api_key,
        "tlsVerify": True,
    }
    if protocol in {"ANTHROPIC_COMPATIBLE", "OPENAI_RESPONSES"}:
        payload["reasoningEffort"] = "high"
    return payload


def test_unified_agent_connection_creates_independent_claude_code_instances(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch, ["CLAUDE_CODE"])

    first = client.post(
        "/api/review-model-connections",
        json=_connection_payload(api_key="deepseek-first-secret"),
    )
    second = client.post(
        "/api/review-model-connections",
        json=_connection_payload(api_key="deepseek-second-secret"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert first_data["runtimeCode"].startswith("AGENT_DEEPSEEK_")
    assert second_data["runtimeCode"].startswith("AGENT_DEEPSEEK_")
    assert first_data["runtimeCode"] != second_data["runtimeCode"]
    assert first_data["displayName"] == "Claude Code + DeepSeek · deepseek-v4-pro[1m]"
    assert second_data["displayName"] == "Claude Code + DeepSeek · deepseek-v4-pro[1m]（2）"
    assert first_data["runnerType"] == "CLAUDE_CODE"
    assert first_data["protocol"] == "ANTHROPIC_COMPATIBLE"
    assert first_data["enabled"] is True
    assert first_data["selected"] is False
    assert first_data["builtIn"] is False
    assert first_data["apiKeyConfigured"] is True
    assert "deepseek-first-secret" not in first.text
    assert "deepseek-second-secret" not in second.text

    first_record = db_session.get(AgentReviewRuntime, first_data["runtimeCode"])
    second_record = db_session.get(AgentReviewRuntime, second_data["runtimeCode"])
    settings = db_session.get(AgentReviewSettings, 1)
    assert first_record.api_key_ciphertext != second_record.api_key_ciphertext
    assert settings.selected_runtime_code == DEFAULT_RUNTIME


def test_unified_agent_connection_maps_openai_anthropic_and_custom_presets(
    client: TestClient,
    monkeypatch,
) -> None:
    _configure_worker(
        client,
        monkeypatch,
        [
            "OPENAI_RESPONSES_AGENT",
            "OPENAI_CHAT_AGENT",
            "ANTHROPIC_MESSAGES_AGENT",
            "CLAUDE_CODE",
        ],
    )
    cases = [
        (
            _connection_payload(
                preset_code="AGENT_OPENAI",
                protocol="OPENAI_RESPONSES",
                base_url="https://api.openai.com/v1",
                model="gpt-5.6-sol",
                api_key="openai-responses-secret",
            ),
            "OPENAI_RESPONSES_AGENT",
        ),
        (
            _connection_payload(
                preset_code="AGENT_OPENAI",
                protocol="OPENAI_CHAT_COMPLETIONS",
                base_url="https://api.openai.com/v1",
                model="gpt-chat",
                api_key="openai-chat-secret",
            ),
            "OPENAI_CHAT_AGENT",
        ),
        (
            _connection_payload(
                preset_code="AGENT_ANTHROPIC",
                protocol="ANTHROPIC_MESSAGES",
                base_url="https://api.anthropic.com/v1",
                model="claude-sonnet-4-5",
                api_key="anthropic-secret",
            ),
            "ANTHROPIC_MESSAGES_AGENT",
        ),
        (
            _connection_payload(
                preset_code="AGENT_CUSTOM",
                protocol="ANTHROPIC_COMPATIBLE",
                base_url="https://custom.example.com/anthropic",
                model="custom-claude-model",
                api_key="custom-secret",
            ),
            "CLAUDE_CODE",
        ),
    ]

    responses = [
        client.post("/api/review-model-connections", json=payload)
        for payload, _runner in cases
    ]

    assert all(response.status_code == 200 for response in responses)
    assert [response.json()["data"]["runnerType"] for response in responses] == [
        expected for _payload, expected in cases
    ]
    assert all(response.json()["data"]["selected"] is False for response in responses)
    serialized = json.dumps([response.json() for response in responses])
    assert "openai-responses-secret" not in serialized
    assert "anthropic-secret" not in serialized


def test_unified_agent_connection_validates_key_preset_url_capability(
    client: TestClient,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch, ["OPENAI_RESPONSES_AGENT"])

    empty_key = client.post(
        "/api/review-model-connections",
        json=_connection_payload(api_key="   "),
    )
    mismatch = client.post(
        "/api/review-model-connections",
        json=_connection_payload(
            preset_code="AGENT_OPENAI",
            protocol="ANTHROPIC_MESSAGES",
        ),
    )
    http_url = client.post(
        "/api/review-model-connections",
        json=_connection_payload(
            preset_code="AGENT_OPENAI",
            protocol="OPENAI_RESPONSES",
            base_url="http://127.0.0.1/v1",
        ),
    )
    unavailable_runner = client.post(
        "/api/review-model-connections",
        json=_connection_payload(),
    )
    client_identity = client.post(
        "/api/review-model-connections",
        json={
            **_connection_payload(),
            "runtimeCode": "CLIENT_CONTROLLED",
            "displayName": "Client controlled",
            "enabled": False,
        },
    )
    assert empty_key.status_code == 400
    assert mismatch.status_code == 400
    assert mismatch.json()["code"] == "REVIEW_MODEL_PRESET_PROTOCOL_MISMATCH"
    assert http_url.status_code == 200
    assert http_url.json()["data"]["baseUrl"] == "http://127.0.0.1/v1"
    assert unavailable_runner.status_code == 409
    assert unavailable_runner.json()["code"] == "AGENT_RUNTIME_RUNNER_UNAVAILABLE"
    assert client_identity.status_code == 400


def _standard_connection_payload(
    *,
    preset_code: str = "STANDARD_OPENAI",
    protocol: str = "OPENAI_RESPONSES",
    base_url: str = "https://api.openai.com/v1/responses",
    model: str = "gpt-5.6-sol",
    api_key: str = "standard-provider-secret",
    reasoning_effort: str | None = "high",
    tls_verify: bool = True,
) -> dict:
    payload = {
        "reviewType": "STANDARD",
        "presetCode": preset_code,
        "protocol": protocol,
        "baseUrl": base_url,
        "model": model,
        "apiKey": api_key,
        "tlsVerify": tls_verify,
    }
    if reasoning_effort is not None:
        payload["reasoningEffort"] = reasoning_effort
    return payload


def test_unified_standard_connection_generates_identity_and_duplicate_names(
    client: TestClient,
    db_session: Session,
) -> None:
    assert client.get("/api/code-quality-review-providers").status_code == 200
    settings = db_session.get(CodeQualityReviewSettings, 1)
    original_default = settings.default_provider_code

    first = client.post(
        "/api/review-model-connections",
        json=_standard_connection_payload(
            api_key="standard-first-secret",
            reasoning_effort="medium",
            tls_verify=False,
        ),
    )
    second = client.post(
        "/api/review-model-connections",
        json=_standard_connection_payload(api_key="standard-second-secret"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert first_data["providerCode"].startswith("STANDARD_OPENAI_")
    assert second_data["providerCode"].startswith("STANDARD_OPENAI_")
    assert first_data["providerCode"] != second_data["providerCode"]
    assert first_data["providerName"] == "OpenAI · gpt-5.6-sol"
    assert second_data["providerName"] == "OpenAI · gpt-5.6-sol（2）"
    assert first_data["providerType"] == "OPENAI_RESPONSES"
    assert first_data["reasoningEffort"] == "medium"
    assert first_data["tlsVerify"] is False
    assert first_data["enabled"] is True
    assert first_data["defaultProvider"] is False
    assert first_data["catalogVisible"] is True
    assert first_data["apiKeyConfigured"] is True
    assert "standard-first-secret" not in first.text
    assert "standard-second-secret" not in second.text
    assert db_session.get(CodeQualityReviewSettings, 1).default_provider_code == original_default


def test_unified_standard_connection_maps_presets_and_validates_contract(
    client: TestClient,
) -> None:
    cases = [
        (
            _standard_connection_payload(
                preset_code="STANDARD_ANTHROPIC",
                protocol="ANTHROPIC_MESSAGES",
                base_url="https://api.anthropic.com/v1/messages",
                model="claude-sonnet-4-5",
                reasoning_effort=None,
            ),
            "ANTHROPIC_MESSAGES",
        ),
        (
            _standard_connection_payload(
                preset_code="STANDARD_DEEPSEEK",
                protocol="OPENAI_CHAT_COMPATIBLE",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                reasoning_effort=None,
            ),
            "OPENAI_CHAT_COMPATIBLE",
        ),
        (
            _standard_connection_payload(
                preset_code="STANDARD_CUSTOM",
                protocol="OPENAI_RESPONSES",
                base_url="https://gateway.example.com/v1/responses",
                model="custom-reasoning-model",
                reasoning_effort="low",
            ),
            "OPENAI_RESPONSES",
        ),
    ]
    responses = [
        client.post("/api/review-model-connections", json=payload)
        for payload, _provider_type in cases
    ]
    assert all(response.status_code == 200 for response in responses)
    assert [response.json()["data"]["providerType"] for response in responses] == [
        provider_type for _payload, provider_type in cases
    ]

    mismatch = client.post(
        "/api/review-model-connections",
        json=_standard_connection_payload(
            protocol="ANTHROPIC_MESSAGES",
            reasoning_effort=None,
        ),
    )
    unsupported_reasoning = client.post(
        "/api/review-model-connections",
        json=_standard_connection_payload(
            preset_code="STANDARD_CUSTOM",
            protocol="OPENAI_CHAT_COMPATIBLE",
            reasoning_effort="high",
        ),
    )
    unsafe_url = client.post(
        "/api/review-model-connections",
        json=_standard_connection_payload(base_url="http://127.0.0.1/v1/responses"),
    )
    client_identity = client.post(
        "/api/review-model-connections",
        json={
            **_standard_connection_payload(),
            "providerCode": "CLIENT_CODE",
            "providerName": "Client Name",
            "enabled": False,
        },
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["code"] == "REVIEW_MODEL_PRESET_PROTOCOL_MISMATCH"
    assert unsupported_reasoning.status_code == 400
    assert unsafe_url.status_code == 400
    assert unsafe_url.json()["code"] == "VALIDATION_ERROR"
    assert client_identity.status_code == 400


def test_standard_clear_key_disables_connection_without_changing_default(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/review-model-connections",
        json=_standard_connection_payload(api_key="clear-me-secret"),
    ).json()["data"]
    provider_code = created["providerCode"]
    assert client.post(
        f"/api/code-quality-review-providers/{provider_code}/set-default"
    ).status_code == 200

    cleared = client.put(
        f"/api/code-quality-review-providers/{provider_code}",
        json={"clearApiKey": True, "enabled": True},
    )

    assert cleared.status_code == 200
    selected = next(
        item for item in cleared.json()["data"]
        if item["providerCode"] == provider_code
    )
    assert selected["catalogVisible"] is True
    assert selected["apiKeyConfigured"] is False
    assert selected["enabled"] is False
    assert selected["defaultProvider"] is True


def test_standard_responses_execution_uses_saved_reasoning_and_tls(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    created = client.post(
        "/api/review-model-connections",
        json=_standard_connection_payload(
            api_key="execution-secret",
            reasoning_effort="low",
            tls_verify=False,
        ),
    ).json()["data"]
    provider = db_session.scalar(
        select(CodeQualityModelProvider).where(
            CodeQualityModelProvider.provider_code == created["providerCode"]
        )
    )
    captured: dict = {}
    monkeypatch.setattr(providers, "_validation_passed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        providers,
        "_run_json_http_provider",
        lambda *_args, **kwargs: captured.update(kwargs) or {"status": "SUCCESS"},
    )

    result = providers._run_openai_responses(
        db_session,
        999,
        provider,
        {"diffText": "+safe()", "changedFiles": ["src/a.py"]},
    )

    assert result["status"] == "SUCCESS"
    assert captured["body"]["reasoning"] == {"effort": "low"}
    assert captured["verify_tls"] is False

    fix_captured: dict = {}
    monkeypatch.setattr(
        providers,
        "_run_text_http_provider",
        lambda *_args, **kwargs: fix_captured.update(kwargs) or {"status": "SUCCESS"},
    )
    fix_result = providers._run_openai_responses_fix(
        db_session,
        1000,
        provider,
        {"diffText": "+safe()", "filePath": "src/a.py", "finding": {}},
    )
    assert fix_result["status"] == "SUCCESS"
    assert fix_captured["body"]["reasoning"] == {"effort": "low"}
    assert fix_captured["verify_tls"] is False


def test_legacy_provider_create_remains_compatible_and_defaults_tls_verify(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/code-quality-review-providers",
        json={
            "providerCode": "LEGACY_H3",
            "providerName": "Legacy H3",
            "providerType": "OPENAI_CHAT_COMPATIBLE",
            "endpointUrl": "https://legacy.example.com/v1",
            "modelName": "legacy-model",
            "apiKey": "legacy-secret",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["tlsVerify"] is True


def test_dynamic_claude_snapshot_configuration_test_claim_fallback_and_delete(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_worker(client, monkeypatch, ["CLAUDE_CODE"])
    created = client.post(
        "/api/review-model-connections",
        json=_connection_payload(
            base_url="https://team-deepseek.example.com/anthropic",
            model="team-deepseek-model",
            api_key="team-deepseek-secret",
        ),
    ).json()["data"]
    runtime_code = created["runtimeCode"]

    selected = client.post(
        f"/api/code-quality-agent-runtimes/{runtime_code}/set-current"
    )
    assert selected.status_code == 200
    selected_snapshot = agent_repository.selected_agent_runtime_snapshot(db_session)
    assert selected_snapshot["runtimeCode"] == runtime_code
    assert selected_snapshot["runnerType"] == "CLAUDE_CODE"
    assert selected_snapshot["baseUrl"] == "https://team-deepseek.example.com/anthropic"
    assert selected_snapshot["model"] == "team-deepseek-model"

    requested = client.post(f"/api/code-quality-agent-runtimes/{runtime_code}/test")
    assert requested.status_code == 200
    claimed_test = client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "connection-worker-token"},
        json={"workerId": "connection-worker"},
    ).json()["data"]
    assert claimed_test["runtime"]["runtimeCode"] == runtime_code
    assert claimed_test["runtime"]["runnerType"] == "CLAUDE_CODE"
    assert claimed_test["runtime"]["baseUrl"] == "https://team-deepseek.example.com/anthropic"
    assert claimed_test["runtime"]["model"] == "team-deepseek-model"
    assert claimed_test["runtime"]["reasoningEffort"] == "high"
    assert claimed_test["runtime"]["apiKey"] == "team-deepseek-secret"
    assert client.post(
        "/internal/agent-review/configuration-test/complete",
        headers={"X-Agent-Worker-Token": "connection-worker-token"},
        json={
            "workerId": "connection-worker",
            "requestId": claimed_test["requestId"],
            "status": "SUCCESS",
            "message": "synthetic claude success",
            "durationMs": 8,
        },
    ).status_code == 200

    snapshot = agent_repository.runtime_record_snapshot(
        db_session.get(AgentReviewRuntime, runtime_code)
    )
    run = agent_repository.create_agent_job(
        db_session,
        task_id=955,
        project_id=77,
        input_payload={
            "worktree": "worktrees/955/head",
            "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=False,
        runtime=snapshot,
    )
    db_session.commit()
    assert run.runner_type == "CLAUDE_CODE"
    assert run.provider == "DEEPSEEK"
    assert "team-deepseek-secret" not in run.input_json
    history = agent_repository.run_to_summary(run)
    assert history["runnerType"] == "CLAUDE_CODE"
    assert history["provider"] == "DEEPSEEK"
    assert history["model"] == "team-deepseek-model"
    claimed = client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "connection-worker-token"},
        json={"workerId": "connection-worker"},
    ).json()["data"]
    assert claimed["runtime"]["runtimeCode"] == runtime_code
    assert claimed["runtime"]["apiKey"] == "team-deepseek-secret"

    fallback_created = client.post(
        "/api/review-model-connections",
        json=_connection_payload(
            model="fallback-model",
            api_key="fallback-secret",
        ),
    ).json()["data"]
    fallback_snapshot = agent_repository.runtime_record_snapshot(
        db_session.get(AgentReviewRuntime, fallback_created["runtimeCode"])
    )
    fallback_run = agent_repository.create_agent_job(
        db_session,
        task_id=956,
        project_id=77,
        input_payload={
            "worktree": "worktrees/956/head",
            "case": {"changedFiles": ["src/b.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=False,
        runtime=fallback_snapshot,
    )
    db_session.commit()
    assert client.put(
        f"/api/code-quality-agent-runtimes/{fallback_created['runtimeCode']}",
        json={"clearApiKey": True},
    ).status_code == 200
    fallback_ids: list[int] = []
    monkeypatch.setattr(
        "app.code_quality.service.schedule_agent_standard_fallback",
        lambda _db, run_id: fallback_ids.append(run_id),
    )
    assert client.post(
        "/internal/agent-review/jobs/claim",
        headers={"X-Agent-Worker-Token": "connection-worker-token"},
        json={"workerId": "connection-worker"},
    ).json()["data"] is None
    assert fallback_ids == [fallback_run.id]

    removable = client.post(
        "/api/review-model-connections",
        json=_connection_payload(model="removable-model", api_key="removable-secret"),
    ).json()["data"]
    deleted = client.delete(
        f"/api/code-quality-agent-runtimes/{removable['runtimeCode']}"
    )
    protected = client.delete(
        f"/api/code-quality-agent-runtimes/{DEFAULT_RUNTIME}"
    )
    assert deleted.status_code == 200
    assert protected.status_code == 409
    assert protected.json()["code"] == "AGENT_RUNTIME_BUILT_IN"
