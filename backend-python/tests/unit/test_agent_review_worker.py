from pathlib import Path
from threading import Event

import pytest

from app.agent_review import worker
from app.agent_review_spike.budgets import default_agent_budgets


def _safe_audit():
    return {
        "phase": "TOOL_ACTIVITY",
        "toolCallCount": 1,
        "evidenceCallsUsed": 1,
        "sourceBytesReturned": 0,
        "diffBytesReturned": 0,
        "blockedAccessCount": 0,
        "reviewSubmitted": False,
        "reviewBudget": {
            "phase": "DISCOVERY",
            "evidenceCallsUsed": 1,
            "evidenceCallsRemaining": 9,
            "sourceBytesRemaining": 200_000,
            "mustSubmit": False,
        },
        "topPathSummaries": [],
        "events": [
            {
                "sequence": 1,
                "tool": "list_files",
                "status": "SUCCESS",
                "durationMs": 1,
                "itemCount": 0,
                "sourceBytes": 0,
                "pathSummary": [],
                "reviewBudget": {
                    "phase": "DISCOVERY",
                    "evidenceCallsUsed": 1,
                    "evidenceCallsRemaining": 9,
                    "sourceBytesRemaining": 200_000,
                    "mustSubmit": False,
                },
            }
        ],
    }


class _OneShotStop:
    def __init__(self):
        self.calls = 0

    def wait(self, _seconds):
        self.calls += 1
        return self.calls > 1


class _NoopThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass

    def join(self, timeout=None):
        pass


def test_job_heartbeat_starts_immediately_and_carries_sequence_and_safe_audit(monkeypatch):
    payloads = []
    latest = worker._LatestAuditSnapshot()
    latest.update(_safe_audit())
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, _path, payload: payloads.append(payload)
        or {"data": {"cancelRequested": False}},
    )

    worker._heartbeat_loop(
        "http://backend",
        "token",
        "worker-1",
        7,
        2,
        _OneShotStop(),
        Event(),
        latest,
    )

    assert payloads == [
        {
            "workerId": "worker-1",
            "claimAttempt": 2,
            "heartbeatSequence": 0,
            "runSummary": {"audit": _safe_audit()},
        },
        {
            "workerId": "worker-1",
            "claimAttempt": 2,
            "heartbeatSequence": 1,
            "runSummary": {"audit": _safe_audit()},
        },
    ]


def test_worker_completion_carries_final_callback_snapshot(tmp_path, monkeypatch):
    requests = []

    def fake_run(*_args, progress_callback=None, **_kwargs):
        progress_callback(_safe_audit())
        return {
            "status": "SUCCESS",
            "reviewCard": {
                "summary": "未发现问题",
                "overallLevel": "LOW",
                "findings": [],
            },
        }

    monkeypatch.setattr(worker, "Thread", _NoopThread)
    monkeypatch.setattr(worker, "_resolve_worktree", lambda _root, _relative: tmp_path)
    monkeypatch.setattr(worker, "run_agent_candidate", fake_run)
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: requests.append((path, payload)) or {},
    )

    worker._run_job(
        "http://backend",
        "token",
        "worker-1",
        tmp_path,
        {
            "jobId": 8,
            "claimAttempt": 1,
            "idempotencyKey": "agent:8",
            "worktree": "worktrees/8/head",
            "input": {},
            "apiKey": "not-inspected",
            "budgets": default_agent_budgets(),
        },
    )

    path, payload = requests[-1]
    assert path == "/internal/agent-review/jobs/8/complete"
    assert payload["claimAttempt"] == 1
    assert payload["runSummary"]["audit"] == _safe_audit()


def test_worker_routes_dynamic_responses_runtime_by_runner_capability(tmp_path, monkeypatch):
    requests = []
    captured = {}

    class FakeResponsesRunner:
        def __init__(self, transport, config):
            captured["transport"] = transport
            captured["config"] = config

        def run(self, case, worktree, *, cancel_event, progress_callback):
            captured["case"] = case
            captured["worktree"] = worktree
            progress_callback(_safe_audit())
            return {
                "status": "SUCCESS",
                "card": {"summary": "未发现问题", "overallLevel": "LOW", "findings": []},
                "toolAudit": _safe_audit(),
            }

    monkeypatch.setattr(worker, "Thread", _NoopThread)
    monkeypatch.setattr(worker, "_resolve_worktree", lambda _root, _relative: tmp_path)
    monkeypatch.setattr(
        worker,
        "HttpxResponsesTransport",
        lambda endpoint, key, *, verify_tls: (endpoint, key, verify_tls),
    )
    monkeypatch.setattr(worker, "OpenAIResponsesAgentRunner", FakeResponsesRunner)
    monkeypatch.setattr(
        worker,
        "run_agent_candidate",
        lambda *_args, **_kwargs: pytest.fail("Claude runner must not handle custom jobs"),
    )
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: requests.append((path, payload)) or {},
    )

    worker._run_job(
        "http://backend",
        "token",
        "worker-1",
        tmp_path,
        {
            "jobId": 88,
            "runId": 98,
            "claimAttempt": 1,
            "idempotencyKey": "agent:88",
            "worktree": "worktrees/88/head",
            "input": {"id": "custom-case", "changedFiles": ["src/service.py"]},
            "runtime": {
                "runtimeCode": "TEAM_RELAY",
                "runtimeType": "TEAM_RELAY",
                "runnerType": "OPENAI_RESPONSES_AGENT",
                "baseUrl": "https://relay.example/v1",
                "model": "gpt-5.6-sol",
                "reasoningEffort": "high",
                "tlsVerify": False,
                "apiKey": "custom-secret",
            },
            "budgets": default_agent_budgets(),
        },
    )

    assert captured["transport"] == (
        "https://relay.example/v1/responses",
        "custom-secret",
        False,
    )
    assert captured["config"].model == "gpt-5.6-sol"
    path, payload = requests[-1]
    assert path == "/internal/agent-review/jobs/88/complete"
    assert payload["reviewCard"]["findings"] == []
    assert payload["runSummary"]["runnerVersion"] == "openai-responses-agent-v1"
    assert payload["runSummary"]["cliVersion"] is None


def test_worker_routes_dynamic_chat_runtime_by_runner_capability(tmp_path, monkeypatch):
    requests = []
    captured = {}

    class FakeChatRunner:
        def __init__(self, transport, config):
            captured["transport"] = transport
            captured["config"] = config

        def run(self, case, worktree, *, cancel_event, progress_callback):
            captured["case"] = case
            captured["worktree"] = worktree
            progress_callback(_safe_audit())
            return {
                "status": "SUCCESS",
                "card": {"summary": "未发现问题", "overallLevel": "LOW", "findings": []},
                "toolAudit": _safe_audit(),
            }

    monkeypatch.setattr(worker, "Thread", _NoopThread)
    monkeypatch.setattr(worker, "_resolve_worktree", lambda _root, _relative: tmp_path)
    monkeypatch.setattr(
        worker,
        "HttpxChatCompletionsTransport",
        lambda endpoint, key, *, verify_tls: (endpoint, key, verify_tls),
    )
    monkeypatch.setattr(worker, "OpenAIChatCompletionsAgentRunner", FakeChatRunner)
    monkeypatch.setattr(
        worker,
        "run_agent_candidate",
        lambda *_args, **_kwargs: pytest.fail("Claude runner must not handle Chat jobs"),
    )
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: requests.append((path, payload)) or {},
    )

    worker._run_job(
        "http://backend",
        "token",
        "worker-1",
        tmp_path,
        {
            "jobId": 89,
            "runId": 99,
            "claimAttempt": 1,
            "idempotencyKey": "agent:89",
            "worktree": "worktrees/89/head",
            "input": {"id": "chat-case", "changedFiles": ["src/service.py"]},
            "runtime": {
                "runtimeCode": "CHAT_AGENT",
                "runtimeType": "CHAT_AGENT",
                "runnerType": "OPENAI_CHAT_AGENT",
                "baseUrl": "https://relay.example/v1",
                "model": "chat-model",
                "tlsVerify": False,
                "apiKey": "chat-secret",
            },
            "budgets": default_agent_budgets(),
        },
    )

    assert captured["transport"] == (
        "https://relay.example/v1/chat/completions",
        "chat-secret",
        False,
    )
    assert captured["config"].model == "chat-model"
    path, payload = requests[-1]
    assert path == "/internal/agent-review/jobs/89/complete"
    assert payload["reviewCard"]["findings"] == []
    assert payload["runSummary"]["runnerVersion"] == "openai-chat-completions-agent-v1"
    assert payload["runSummary"]["cliVersion"] is None


def test_worker_routes_dynamic_anthropic_runtime_by_runner_capability(
    tmp_path, monkeypatch
):
    requests = []
    captured = {}

    class FakeAnthropicRunner:
        def __init__(self, transport, config):
            captured["transport"] = transport
            captured["config"] = config

        def run(self, case, worktree, *, cancel_event, progress_callback):
            progress_callback(_safe_audit())
            return {
                "status": "SUCCESS",
                "card": {"summary": "未发现问题", "overallLevel": "LOW", "findings": []},
                "toolAudit": _safe_audit(),
            }

    monkeypatch.setattr(worker, "Thread", _NoopThread)
    monkeypatch.setattr(worker, "_resolve_worktree", lambda _root, _relative: tmp_path)
    monkeypatch.setattr(
        worker,
        "HttpxAnthropicMessagesTransport",
        lambda endpoint, key, *, verify_tls: (endpoint, key, verify_tls),
    )
    monkeypatch.setattr(worker, "AnthropicMessagesAgentRunner", FakeAnthropicRunner)
    monkeypatch.setattr(
        worker,
        "run_agent_candidate",
        lambda *_args, **_kwargs: pytest.fail("Claude runner must not handle Anthropic jobs"),
    )
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: requests.append((path, payload)) or {},
    )

    worker._run_job(
        "http://backend",
        "token",
        "worker-1",
        tmp_path,
        {
            "jobId": 90,
            "runId": 100,
            "claimAttempt": 1,
            "idempotencyKey": "agent:90",
            "worktree": "worktrees/90/head",
            "input": {"id": "anthropic-case", "changedFiles": ["src/service.py"]},
            "runtime": {
                "runtimeCode": "ANTHROPIC_AGENT",
                "runtimeType": "ANTHROPIC_AGENT",
                "runnerType": "ANTHROPIC_MESSAGES_AGENT",
                "baseUrl": "https://relay.example/v1",
                "model": "claude-sonnet",
                "tlsVerify": False,
                "apiKey": "anthropic-secret",
            },
            "budgets": default_agent_budgets(),
        },
    )

    assert captured["transport"] == (
        "https://relay.example/v1/messages",
        "anthropic-secret",
        False,
    )
    assert captured["config"].model == "claude-sonnet"
    path, payload = requests[-1]
    assert path == "/internal/agent-review/jobs/90/complete"
    assert payload["reviewCard"]["findings"] == []
    assert payload["runSummary"]["runnerVersion"] == "anthropic-messages-agent-v1"
    assert payload["runSummary"]["cliVersion"] is None


def test_worker_routes_dynamic_claude_runtime_with_snapshot_configuration(
    tmp_path,
    monkeypatch,
):
    requests = []
    captured = []

    def fake_run(case, worktree, api_key, config, **kwargs):
        captured.append((case, worktree, api_key, config))
        progress_callback = kwargs.get("progress_callback")
        if progress_callback is not None:
            progress_callback(_safe_audit())
        return {
            "status": "SUCCESS",
            "reviewCard": {
                "summary": "未发现问题",
                "overallLevel": "LOW",
                "findings": [],
            },
        }

    runtime = {
        "runtimeCode": "AGENT_DEEPSEEK_DYNAMIC",
        "runtimeType": "AGENT_DEEPSEEK_DYNAMIC",
        "runnerType": "CLAUDE_CODE",
        "baseUrl": "https://team-deepseek.example.com/anthropic",
        "model": "team-deepseek-model",
        "reasoningEffort": "medium",
        "tlsVerify": False,
        "apiKey": "team-deepseek-secret",
    }
    monkeypatch.setattr(worker, "Thread", _NoopThread)
    monkeypatch.setattr(worker, "_resolve_worktree", lambda _root, _relative: tmp_path)
    monkeypatch.setattr(worker, "run_agent_candidate", fake_run)
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: requests.append((path, payload)) or {},
    )

    worker._run_job(
        "http://backend",
        "token",
        "worker-1",
        tmp_path,
        {
            "jobId": 91,
            "runId": 101,
            "claimAttempt": 1,
            "idempotencyKey": "agent:91",
            "worktree": "worktrees/91/head",
            "input": {"id": "claude-case", "changedFiles": ["src/service.py"]},
            "runtime": runtime,
            "budgets": default_agent_budgets(),
        },
    )
    worker._run_configuration_test(
        "http://backend",
        "token",
        "worker-1",
        {
            "kind": "CONFIG_TEST",
            "requestId": "runtime-test:AGENT_DEEPSEEK_DYNAMIC:1",
            "runtime": runtime,
            "budgets": default_agent_budgets(),
        },
    )

    assert len(captured) == 2
    for _case, _worktree, api_key, config in captured:
        assert api_key == "team-deepseek-secret"
        assert config.base_url == "https://team-deepseek.example.com/anthropic"
        assert config.model == "team-deepseek-model"
        assert config.reasoning_effort == "medium"
        assert config.tls_verify is False
    assert requests[0][0] == "/internal/agent-review/jobs/91/complete"
    assert requests[-1][0] == "/internal/agent-review/configuration-test/complete"
    assert requests[-1][1]["status"] == "SUCCESS"


def test_dynamic_runtime_configuration_test_uses_synthetic_workspace(monkeypatch):
    requests = []
    captured = {}

    class FakeResponsesRunner:
        def __init__(self, transport, config):
            captured["transport"] = transport
            captured["config"] = config

        def run(self, case, worktree):
            captured["case"] = case
            captured["worktreeFiles"] = sorted(path.name for path in worktree.iterdir())
            return {"status": "SUCCESS"}

    monkeypatch.setattr(
        worker,
        "HttpxResponsesTransport",
        lambda endpoint, key, *, verify_tls: (endpoint, key, verify_tls),
    )
    monkeypatch.setattr(worker, "OpenAIResponsesAgentRunner", FakeResponsesRunner)
    monkeypatch.setattr(
        worker,
        "run_agent_candidate",
        lambda *_args, **_kwargs: pytest.fail("Claude runner must not handle Responses tests"),
    )
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: requests.append((path, payload)) or {},
    )

    worker._run_configuration_test(
        "http://backend",
        "token",
        "worker-1",
        {
            "kind": "CONFIG_TEST",
            "requestId": "runtime-test:TEAM_RELAY:1",
            "runtime": {
                "runtimeCode": "TEAM_RELAY",
                "runtimeType": "TEAM_RELAY",
                "runnerType": "OPENAI_RESPONSES_AGENT",
                "baseUrl": "https://relay.example/v1",
                "model": "gpt-5.6-sol",
                "reasoningEffort": "high",
                "tlsVerify": True,
                "apiKey": "synthetic-secret",
            },
            "budgets": default_agent_budgets(),
        },
    )

    assert captured["transport"] == (
        "https://relay.example/v1/responses",
        "synthetic-secret",
        True,
    )
    assert captured["case"]["id"] == "configuration-test"
    assert captured["case"]["changedFiles"] == ["healthcheck.txt"]
    assert captured["worktreeFiles"] == ["healthcheck.txt"]
    path, payload = requests[-1]
    assert path == "/internal/agent-review/configuration-test/complete"
    assert payload["requestId"] == "runtime-test:TEAM_RELAY:1"
    assert payload["status"] == "SUCCESS"


def test_chat_runtime_configuration_test_uses_chat_runner(monkeypatch):
    requests = []
    captured = {}

    class FakeChatRunner:
        def __init__(self, transport, config):
            captured["transport"] = transport
            captured["config"] = config

        def run(self, case, worktree):
            captured["case"] = case
            captured["worktreeFiles"] = sorted(path.name for path in worktree.iterdir())
            return {"status": "SUCCESS"}

    monkeypatch.setattr(
        worker,
        "HttpxChatCompletionsTransport",
        lambda endpoint, key, *, verify_tls: (endpoint, key, verify_tls),
    )
    monkeypatch.setattr(worker, "OpenAIChatCompletionsAgentRunner", FakeChatRunner)
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: requests.append((path, payload)) or {},
    )

    worker._run_configuration_test(
        "http://backend",
        "token",
        "worker-1",
        {
            "kind": "CONFIG_TEST",
            "requestId": "runtime-test:CHAT_AGENT:1",
            "runtime": {
                "runtimeCode": "CHAT_AGENT",
                "runtimeType": "CHAT_AGENT",
                "runnerType": "OPENAI_CHAT_AGENT",
                "baseUrl": "https://relay.example/v1",
                "model": "chat-model",
                "tlsVerify": True,
                "apiKey": "synthetic-chat-secret",
            },
            "budgets": default_agent_budgets(),
        },
    )

    assert captured["transport"] == (
        "https://relay.example/v1/chat/completions",
        "synthetic-chat-secret",
        True,
    )
    assert captured["case"]["changedFiles"] == ["healthcheck.txt"]
    assert captured["worktreeFiles"] == ["healthcheck.txt"]
    path, payload = requests[-1]
    assert path == "/internal/agent-review/configuration-test/complete"
    assert payload["status"] == "SUCCESS"
    assert "Chat Completions" in payload["message"]


def test_anthropic_runtime_configuration_test_uses_messages_runner(monkeypatch):
    requests = []
    captured = {}

    class FakeAnthropicRunner:
        def __init__(self, transport, config):
            captured["transport"] = transport
            captured["config"] = config

        def run(self, case, worktree):
            captured["case"] = case
            captured["worktreeFiles"] = sorted(path.name for path in worktree.iterdir())
            return {"status": "SUCCESS"}

    monkeypatch.setattr(
        worker,
        "HttpxAnthropicMessagesTransport",
        lambda endpoint, key, *, verify_tls: (endpoint, key, verify_tls),
    )
    monkeypatch.setattr(worker, "AnthropicMessagesAgentRunner", FakeAnthropicRunner)
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: requests.append((path, payload)) or {},
    )

    worker._run_configuration_test(
        "http://backend",
        "token",
        "worker-1",
        {
            "kind": "CONFIG_TEST",
            "requestId": "runtime-test:ANTHROPIC_AGENT:1",
            "runtime": {
                "runtimeCode": "ANTHROPIC_AGENT",
                "runtimeType": "ANTHROPIC_AGENT",
                "runnerType": "ANTHROPIC_MESSAGES_AGENT",
                "baseUrl": "https://relay.example/v1",
                "model": "claude-sonnet",
                "tlsVerify": True,
                "apiKey": "synthetic-anthropic-secret",
            },
            "budgets": default_agent_budgets(),
        },
    )

    assert captured["transport"] == (
        "https://relay.example/v1/messages",
        "synthetic-anthropic-secret",
        True,
    )
    assert captured["config"].model == "claude-sonnet"
    assert captured["case"]["changedFiles"] == ["healthcheck.txt"]
    assert captured["worktreeFiles"] == ["healthcheck.txt"]
    path, payload = requests[-1]
    assert path == "/internal/agent-review/configuration-test/complete"
    assert payload["status"] == "SUCCESS"
    assert "Anthropic Messages" in payload["message"]


@pytest.mark.parametrize(
    ("runtime", "expected"),
    [({}, True), ({"tlsVerify": True}, True), ({"tlsVerify": False}, False), ({"tlsVerify": "false"}, True)],
)
def test_custom_tls_verify_requires_explicit_false(runtime, expected):
    assert worker._custom_tls_verify(runtime) is expected


def test_worker_maps_all_runtime_budgets_to_runner_config() -> None:
    budgets = {
        "maxTurns": 14,
        "maxToolCalls": 50,
        "maxSourceBytes": 250_000,
        "timeoutSeconds": 700,
        "inlineDiffBytes": 240_000,
        "maxEvidenceCalls": 12,
        "convergeAtCalls": 10,
        "submitByTurn": 11,
    }

    config = worker._runner_config_from_budgets(budgets)

    assert config.max_turns == 14
    assert config.max_tool_calls == 50
    assert config.max_source_bytes == 250_000
    assert config.timeout_seconds == 700
    assert config.inline_diff_bytes == 240_000
    assert config.max_evidence_calls == 12
    assert config.converge_at_calls == 10
    assert config.submit_by_turn == 11


def test_worker_rejects_invalid_internal_budget_contract(tmp_path, monkeypatch):
    requests = []
    runner_called = False

    def unexpected_runner(*_args, **_kwargs):
        nonlocal runner_called
        runner_called = True
        return {}

    monkeypatch.setattr(worker, "Thread", _NoopThread)
    monkeypatch.setattr(worker, "_resolve_worktree", lambda _root, _relative: tmp_path)
    monkeypatch.setattr(worker, "run_agent_candidate", unexpected_runner)
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: requests.append((path, payload)) or {},
    )

    worker._run_job(
        "http://backend",
        "token",
        "worker-1",
        tmp_path,
        {
            "jobId": 18,
            "claimAttempt": 1,
            "idempotencyKey": "agent:18",
            "worktree": "worktrees/18/head",
            "input": {},
            "apiKey": "not-inspected",
            "budgets": {"invalidBudgetContract": 1},
        },
    )

    path, payload = requests[-1]
    assert runner_called is False
    assert path == "/internal/agent-review/jobs/18/fail"
    assert payload["failureCode"] == "AGENT_INVALID_BUDGET_CONFIG"


def test_worker_unexpected_error_logs_only_safe_type_and_location(
    tmp_path, monkeypatch, caplog
):
    requests = []

    def fail_without_leaking(*_args, **_kwargs):
        raise RuntimeError("SECRET_PROMPT_AND_SOURCE")

    monkeypatch.setattr(worker, "Thread", _NoopThread)
    monkeypatch.setattr(worker, "_resolve_worktree", lambda _root, _relative: tmp_path)
    monkeypatch.setattr(worker, "run_agent_candidate", fail_without_leaking)
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: requests.append((path, payload)) or {},
    )

    worker._run_job(
        "http://backend",
        "token",
        "worker-1",
        tmp_path,
        {
            "jobId": 9,
            "claimAttempt": 1,
            "idempotencyKey": "agent:9",
            "worktree": "worktrees/9/head",
            "input": {},
            "apiKey": "not-inspected",
            "budgets": {},
        },
    )

    path, payload = requests[-1]
    assert path == "/internal/agent-review/jobs/9/fail"
    assert payload["failureCode"] == "AGENT_WORKER_ERROR"
    assert "RuntimeError" in caplog.text
    assert "test_agent_review_worker.py" in caplog.text
    assert "SECRET_PROMPT_AND_SOURCE" not in caplog.text


def test_worker_process_heartbeat_starts_immediately(monkeypatch):
    payloads = []
    activity = worker._WorkerActivityState()
    activity.begin({"jobId": 31, "runId": 41})
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: payloads.append((path, payload)) or {},
    )

    worker._worker_heartbeat_loop(
        "http://backend",
        "token",
        "worker-process-1",
        _OneShotStop(),
        activity,
    )

    assert [path for path, _payload in payloads] == [
        "/internal/agent-review/workers/heartbeat",
        "/internal/agent-review/workers/heartbeat",
    ]
    assert all(
        payload["workerId"] == "worker-process-1"
        for _path, payload in payloads
    )
    assert all(
        payload["state"] == "BUSY"
        and payload["capacity"] == 1
        and payload["activeJobId"] == 31
        and payload["activeRunId"] == 41
        for _path, payload in payloads
    )


def test_worker_activity_state_returns_to_idle() -> None:
    activity = worker._WorkerActivityState()

    activity.begin({"jobId": 7, "runId": 9})
    assert activity.snapshot() == {
        "state": "BUSY",
        "capacity": 1,
        "activeJobId": 7,
        "activeRunId": 9,
    }

    activity.idle()
    assert activity.snapshot() == {"state": "IDLE", "capacity": 1}


def test_idle_sigterm_enters_draining_stops_claim_and_is_idempotent(
    tmp_path,
    monkeypatch,
) -> None:
    activity = worker._WorkerActivityState()
    wake = Event()
    drain = worker._DrainController(activity, wake)
    claims = []
    monkeypatch.setattr(
        worker,
        "_post",
        lambda *_args, **_kwargs: claims.append(True) or {"data": None},
    )

    assert drain.request() is True
    assert drain.request() is False
    assert wake.is_set()
    assert activity.snapshot() == {"state": "DRAINING", "capacity": 1}

    result = worker._worker_loop(
        "http://backend",
        "token",
        "worker-idle",
        tmp_path,
        1,
        activity,
        drain,
    )

    assert result == 0
    assert claims == []


def test_busy_sigterm_keeps_current_job_finishes_and_does_not_claim_again(
    tmp_path,
    monkeypatch,
) -> None:
    activity = worker._WorkerActivityState()
    drain = worker._DrainController(activity, Event())
    claims = []
    completed = []
    job = {
        "jobId": 51,
        "runId": 61,
        "claimAttempt": 1,
        "idempotencyKey": "agent:51",
    }

    def fake_post(_url, _token, path, _payload):
        claims.append(path)
        return {"data": job}

    def fake_run(*_args):
        assert activity.snapshot() == {
            "state": "BUSY",
            "capacity": 1,
            "activeJobId": 51,
            "activeRunId": 61,
        }
        assert drain.request() is True
        assert activity.snapshot()["state"] == "DRAINING"
        completed.append(True)

    monkeypatch.setattr(worker, "_post", fake_post)
    monkeypatch.setattr(worker, "_run_job", fake_run)

    result = worker._worker_loop(
        "http://backend",
        "token",
        "worker-busy",
        tmp_path,
        1,
        activity,
        drain,
    )

    assert result == 0
    assert completed == [True]
    assert claims == ["/internal/agent-review/jobs/claim"]
    assert activity.snapshot() == {"state": "DRAINING", "capacity": 1}


def test_draining_worker_heartbeat_continues_with_safe_active_references(
    monkeypatch,
) -> None:
    payloads = []
    activity = worker._WorkerActivityState()
    activity.begin({"jobId": 71, "runId": 81})
    activity.drain()
    monkeypatch.setattr(
        worker,
        "_post",
        lambda _url, _token, path, payload: payloads.append((path, payload)) or {},
    )

    worker._worker_heartbeat_loop(
        "http://backend",
        "token",
        "worker-draining",
        _OneShotStop(),
        activity,
    )

    assert len(payloads) == 2
    assert all(
        path == "/internal/agent-review/workers/heartbeat"
        and payload == {
            "workerId": "worker-draining",
            "workerVersion": worker.WORKER_VERSION,
            "cliVersion": worker.CLI_VERSION,
            "capabilities": worker.WORKER_CAPABILITIES,
            "responsesRunnerVersion": worker.RESPONSES_RUNNER_VERSION,
            "state": "DRAINING",
            "capacity": 1,
            "activeJobId": 71,
            "activeRunId": 81,
        }
        for path, payload in payloads
    )


def test_shutdown_watchdog_forces_exit_only_after_grace_is_exhausted() -> None:
    activity = worker._WorkerActivityState()
    drain = worker._DrainController(activity, Event())
    process_stop = Event()
    exits = []
    drain.request()

    worker._shutdown_watchdog(
        drain,
        process_stop,
        grace_seconds=0,
        force_exit=lambda code: exits.append(code),
    )

    assert exits == [0]
    assert worker.AGENT_WORKER_SHUTDOWN_GRACE_SECONDS == 930


def test_worker_healthcheck_uses_derived_worker_registration(monkeypatch):
    monkeypatch.setattr(
        worker,
        "_fetch_agent_settings",
        lambda _url: {
            "workerPool": {
                "nodes": [
                    {"workerId": "pool-container-a", "online": True},
                    {"workerId": "pool-container-b", "online": False},
                ]
            }
        },
    )

    assert worker._healthcheck("http://backend", "pool-container-a") == 0
    assert worker._healthcheck("http://backend", "pool-container-b") == 1
    assert worker._healthcheck("http://backend", "pool-container-c") == 1
    monkeypatch.setattr(
        worker,
        "_fetch_agent_settings",
        lambda _url: {"workerPool": "malformed"},
    )
    assert worker._healthcheck("http://backend", "pool-container-a") == 1


def test_worker_healthcheck_mode_does_not_require_runtime_secret_or_workspace(
    monkeypatch,
):
    monkeypatch.setenv("AGENT_REVIEW_BACKEND_URL", "http://backend")
    monkeypatch.setenv("AGENT_REVIEW_WORKER_ID", "local-worker-1")
    monkeypatch.delenv("AGENT_REVIEW_WORKER_TOKEN", raising=False)
    monkeypatch.setattr(worker.sys, "argv", ["worker.py", "--healthcheck"])
    monkeypatch.setattr(worker, "_healthcheck", lambda _url, _worker_id: 0)

    assert worker.main() == 0


def test_worker_id_supports_explicit_and_hostname_derived_values(monkeypatch):
    monkeypatch.setenv("AGENT_REVIEW_WORKER_ID", "local-worker-1")
    assert worker._resolve_worker_id() == "local-worker-1"

    monkeypatch.delenv("AGENT_REVIEW_WORKER_ID")
    monkeypatch.setenv("AGENT_REVIEW_WORKER_ID_PREFIX", "pool")
    monkeypatch.setattr(worker.socket, "gethostname", lambda: "container-abc")
    assert worker._resolve_worker_id() == "pool-container-abc"


def test_worker_id_rejects_unsafe_values(monkeypatch):
    monkeypatch.setenv("AGENT_REVIEW_WORKER_ID", "worker/../../unsafe")

    with pytest.raises(ValueError, match="letters, numbers"):
        worker._resolve_worker_id()


def test_worker_compose_files_use_prefix_ids_and_registration_healthcheck() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    for relative_path in (
        "deploy/docker-compose.yml",
        "deploy/docker-compose.runtime.yml",
        "deploy/docker-compose.windows-agent.yml",
    ):
        text = (repository_root / relative_path).read_text(encoding="utf-8")
        worker_section = text.split("\n  agent-worker:", 1)[1].split(
            "\n  agent-egress-proxy:", 1
        )[0]

        assert "AGENT_REVIEW_WORKER_ID_PREFIX:" in worker_section
        assert "HTTP_PROXY: http://agent-egress-proxy:3128" in worker_section
        assert "HTTPS_PROXY: http://agent-egress-proxy:3128" in worker_section
        assert "app.agent_review.worker" in worker_section
        assert "--healthcheck" in worker_section
        assert "stop_grace_period: 930s" in worker_section
        assert "agent-worker-1" not in worker_section
        if "windows-agent" not in relative_path:
            assert "\n      AGENT_REVIEW_WORKER_ID:" not in worker_section


def test_stage3_deploy_helper_is_safe_and_included_in_offline_package() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    deploy_script = (
        repository_root / "deploy/deploy-stage3.sh"
    ).read_text(encoding="utf-8")
    package_script = (
        repository_root / "scripts/package-docker-deploy.ps1"
    ).read_text(encoding="utf-8")

    assert "status|preflight|upgrade|scale" in deploy_script
    assert "queueMetrics" in deploy_script
    assert "set_agent_enabled false" in deploy_script
    assert "AGENT_PAUSED_BY_SCRIPT=true" in deploy_script
    assert 'compose up -d --no-deps --scale "agent-worker=$WORKERS"' in deploy_script
    assert "onlineCapacity >= $target and drainingWorkers=0" in deploy_script
    assert "cleanup_stopped_project_containers()" in deploy_script
    assert 'com.docker.compose.project' in deploy_script
    assert "for state in created exited dead" in deploy_script
    assert '--filter "status=$state"' in deploy_script
    assert 'docker rm "$container_id"' in deploy_script
    assert deploy_script.count("cleanup_stopped_project_containers") == 3
    assert "docker rm -f" not in deploy_script
    assert "docker system prune" not in deploy_script
    assert "docker volume prune" not in deploy_script
    upgrade_section = deploy_script.split("\n  upgrade)", 1)[1].split(
        "\n  scale)", 1
    )[0]
    scale_section = deploy_script.split("\n  scale)", 1)[1]
    for command_section in (upgrade_section, scale_section):
        final_status_index = command_section.index(
            'load_snapshot || fail "Could not read final Agent status"'
        )
        cleanup_index = command_section.index("cleanup_stopped_project_containers")
        assert final_status_index < cleanup_index
    assert "--keep-agent-enabled" not in deploy_script
    assert "apiKey" not in deploy_script
    assert "deploy-stage3.sh" in package_script
    assert 'chmod +x "`$DEPLOY_HOME/deploy-stage3.sh"' in package_script
    assert "./deploy-stage3.sh upgrade --workers 2" in package_script
