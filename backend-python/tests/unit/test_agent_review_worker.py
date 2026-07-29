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
        assert "app.agent_review.worker" in worker_section
        assert "--healthcheck" in worker_section
        assert "agent-worker-1" not in worker_section
        if "windows-agent" not in relative_path:
            assert "\n      AGENT_REVIEW_WORKER_ID:" not in worker_section
