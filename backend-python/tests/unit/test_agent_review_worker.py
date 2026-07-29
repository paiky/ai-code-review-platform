from threading import Event

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
        _OneShotStop(),
        Event(),
        latest,
    )

    assert payloads == [
        {
            "workerId": "worker-1",
            "heartbeatSequence": 0,
            "runSummary": {"audit": _safe_audit()},
        },
        {
            "workerId": "worker-1",
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
            "idempotencyKey": "agent:8",
            "worktree": "worktrees/8/head",
            "input": {},
            "apiKey": "not-inspected",
            "budgets": default_agent_budgets(),
        },
    )

    path, payload = requests[-1]
    assert path == "/internal/agent-review/jobs/8/complete"
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
