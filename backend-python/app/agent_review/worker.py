from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import socket
from threading import Event, Lock, Thread
import tempfile
import time
import traceback
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.agent_review_spike.budgets import (
    AgentBudgetValidationError,
    validate_agent_budgets,
)
from app.agent_review_spike.runner import RunnerConfig, run_agent_candidate


WORKER_VERSION = "agent-worker-v1"
CLI_VERSION = "2.1.112"
_LOGGER = logging.getLogger(__name__)


class _LatestAuditSnapshot:
    def __init__(self) -> None:
        self._lock = Lock()
        self._value: dict[str, Any] = {}

    def update(self, value: dict[str, Any]) -> None:
        if not isinstance(value, dict):
            return
        with self._lock:
            self._value = json.loads(json.dumps(value, ensure_ascii=False))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._value, ensure_ascii=False))


def main() -> int:
    backend_url = _required_env("AGENT_REVIEW_BACKEND_URL").rstrip("/")
    token = _required_env("AGENT_REVIEW_WORKER_TOKEN")
    worker_id = _resolve_worker_id()
    workspace_root = Path(os.getenv("AGENT_REVIEW_WORKSPACE_ROOT", "/workspaces")).resolve(strict=True)
    poll_seconds = max(float(os.getenv("AGENT_REVIEW_WORKER_POLL_SECONDS", "3")), 1.0)
    process_stop = Event()
    process_heartbeat = Thread(
        target=_worker_heartbeat_loop,
        args=(backend_url, token, worker_id, process_stop),
        daemon=True,
    )
    process_heartbeat.start()
    try:
        while True:
            try:
                claimed = _post(
                    backend_url,
                    token,
                    "/internal/agent-review/jobs/claim",
                    {"workerId": worker_id},
                )
                job = claimed.get("data")
                if job:
                    _run_job(backend_url, token, worker_id, workspace_root, job)
                    continue
            except (OSError, ValueError, HTTPError, URLError):
                pass
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        return 0
    finally:
        process_stop.set()
        process_heartbeat.join(timeout=2)


def _run_job(
    backend_url: str, token: str, worker_id: str, workspace_root: Path, job: dict[str, Any]
) -> None:
    if job.get("kind") == "CONFIG_TEST":
        _run_configuration_test(backend_url, token, worker_id, job)
        return
    job_id = int(job["jobId"])
    claim_attempt = int(job["claimAttempt"])
    stop = Event()
    cancelled = Event()
    latest_audit = _LatestAuditSnapshot()
    heartbeat = Thread(
        target=_heartbeat_loop,
        args=(
            backend_url,
            token,
            worker_id,
            job_id,
            claim_attempt,
            stop,
            cancelled,
            latest_audit,
        ),
        daemon=True,
    )
    heartbeat.start()
    try:
        runner_config = _runner_config_from_budgets(job.get("budgets"))
        worktree = _resolve_worktree(workspace_root, str(job.get("worktree") or ""))
        summary = run_agent_candidate(
            job.get("input") or {},
            worktree,
            str(job.get("apiKey") or ""),
            runner_config,
            cancel_event=cancelled,
            progress_callback=latest_audit.update,
        )
        final_audit = latest_audit.snapshot()
        if final_audit:
            summary["audit"] = final_audit
        base = {
            "workerId": worker_id,
            "claimAttempt": claim_attempt,
            "idempotencyKey": job["idempotencyKey"],
            "runSummary": summary,
        }
        if cancelled.is_set():
            _post(backend_url, token, f"/internal/agent-review/jobs/{job_id}/cancelled", base)
        elif summary.get("status") == "SUCCESS" and isinstance(summary.get("reviewCard"), dict):
            _post(backend_url, token, f"/internal/agent-review/jobs/{job_id}/complete", {**base, "reviewCard": summary["reviewCard"]})
        else:
            error_code = summary.get("errorCode") or "AGENT_RUN_FAILED"
            _post(backend_url, token, f"/internal/agent-review/jobs/{job_id}/fail", {
                **base,
                "failureCode": error_code,
                "failureMessage": _failure_message(error_code),
            })
    except Exception as exception:
        error_code = (
            "AGENT_INVALID_BUDGET_CONFIG"
            if isinstance(exception, AgentBudgetValidationError)
            else "AGENT_WORKER_ERROR"
        )
        _LOGGER.error(
            "Agent Worker job failed before terminal report: jobId=%s exceptionType=%s location=%s",
            job_id,
            type(exception).__name__,
            _safe_exception_location(exception),
        )
        _post(backend_url, token, f"/internal/agent-review/jobs/{job_id}/fail", {
            "workerId": worker_id,
            "claimAttempt": claim_attempt,
            "idempotencyKey": job["idempotencyKey"],
            "failureCode": error_code,
            "failureMessage": _failure_message(error_code),
            "runSummary": {"audit": latest_audit.snapshot()},
        })
    finally:
        stop.set()
        heartbeat.join(timeout=2)


def _run_configuration_test(
    backend_url: str, token: str, worker_id: str, job: dict[str, Any]
) -> None:
    started = time.perf_counter()
    status = "FAILED"
    message = "Agent configuration test failed"
    try:
        budgets = job.get("budgets") or {}
        with tempfile.TemporaryDirectory(prefix="agent-config-test-") as temporary_name:
            worktree = Path(temporary_name)
            (worktree / "healthcheck.txt").write_text("agent_review_healthcheck=true\n", encoding="utf-8")
            summary = run_agent_candidate(
                {
                    "id": "configuration-test",
                    "title": "Agent Review configuration test; submit an empty review",
                    "baseRef": "none",
                    "commitSha": "none",
                    "changedFiles": ["healthcheck.txt"],
                    "diff": "+agent_review_healthcheck=true",
                    "diffMode": "INLINE",
                    "baselineContext": "No production source is included in this configuration test.",
                    "reviewInstructions": "This is a connectivity test. Report no findings and submit the Review Card.",
                    "targetFinding": {"filePath": "healthcheck.txt", "startLine": 1, "endLine": 1},
                },
                worktree,
                str(job.get("apiKey") or ""),
                RunnerConfig(
                    timeout_seconds=int(budgets.get("timeoutSeconds") or 180),
                    max_turns=int(budgets.get("maxTurns") or 4),
                    max_tool_calls=int(budgets.get("maxToolCalls") or 8),
                    max_source_bytes=int(budgets.get("maxSourceBytes") or 10_000),
                ),
            )
        status = "SUCCESS" if summary.get("status") == "SUCCESS" else "FAILED"
        message = "Claude Code + DeepSeek + read-only MCP connectivity succeeded" if status == "SUCCESS" else str(summary.get("errorCode") or message)
    except Exception as exception:
        message = str(exception)[:500]
    _post(
        backend_url,
        token,
        "/internal/agent-review/configuration-test/complete",
        {
            "workerId": worker_id,
            "requestId": job["requestId"],
            "status": status,
            "message": message,
            "durationMs": int((time.perf_counter() - started) * 1000),
        },
    )


def _worker_heartbeat_loop(backend_url: str, token: str, worker_id: str, stop: Event) -> None:
    while True:
        try:
            _post(
                backend_url,
                token,
                "/internal/agent-review/workers/heartbeat",
                {"workerId": worker_id, "workerVersion": WORKER_VERSION, "cliVersion": CLI_VERSION},
            )
        except Exception:
            pass
        if stop.wait(15):
            return


def _heartbeat_loop(
    backend_url: str,
    token: str,
    worker_id: str,
    job_id: int,
    claim_attempt: int,
    stop: Event,
    cancelled: Event,
    latest_audit: _LatestAuditSnapshot,
) -> None:
    heartbeat_sequence = 0
    while True:
        try:
            payload: dict[str, Any] = {
                "workerId": worker_id,
                "claimAttempt": claim_attempt,
                "heartbeatSequence": heartbeat_sequence,
            }
            audit = latest_audit.snapshot()
            if audit:
                payload["runSummary"] = {"audit": audit}
            response = _post(
                backend_url,
                token,
                f"/internal/agent-review/jobs/{job_id}/heartbeat",
                payload,
            )
            if bool((response.get("data") or {}).get("cancelRequested")):
                cancelled.set()
        except Exception:
            pass
        heartbeat_sequence += 1
        if stop.wait(15):
            return


def _resolve_worktree(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError("worktree must be a relative path")
    resolved = (root / relative).resolve(strict=True)
    resolved.relative_to(root)
    if not resolved.is_dir():
        raise ValueError("worktree is unavailable")
    return resolved


def _post(base_url: str, token: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        base_url + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Agent-Worker-Token": token},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        value = json.loads(response.read().decode("utf-8"))
    return value if isinstance(value, dict) else {}


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _resolve_worker_id() -> str:
    explicit = str(os.getenv("AGENT_REVIEW_WORKER_ID") or "").strip()
    if explicit:
        worker_id = explicit
    else:
        prefix = str(
            os.getenv("AGENT_REVIEW_WORKER_ID_PREFIX") or "agent-worker"
        ).strip() or "agent-worker"
        hostname = socket.gethostname().strip()
        worker_id = f"{prefix}-{hostname}"
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", worker_id):
        raise ValueError(
            "Agent Review Worker ID must contain only letters, numbers, dot, "
            "underscore, or hyphen and be at most 128 characters"
        )
    return worker_id


def _failure_message(error_code: str) -> str:
    if error_code == "AGENT_INVALID_BUDGET_CONFIG":
        return "Agent Review rejected an invalid runtime budget contract"
    if error_code == "AGENT_MAX_TURNS_EXCEEDED":
        return "Agent Review reached the turn budget before submitting a Review Card"
    if error_code == "AGENT_CLI_FAILED":
        return "Claude CLI exited with a non-zero status before submitting a Review Card"
    if error_code == "AGENT_WORKER_ERROR":
        return "Agent Worker failed before a valid Review Card could be submitted"
    return "Agent Review did not produce a valid submitted Review Card"


def _runner_config_from_budgets(value: Any) -> RunnerConfig:
    budgets = validate_agent_budgets(value)
    return RunnerConfig(
        timeout_seconds=budgets["timeoutSeconds"],
        max_turns=budgets["maxTurns"],
        max_tool_calls=budgets["maxToolCalls"],
        max_source_bytes=budgets["maxSourceBytes"],
        inline_diff_bytes=budgets["inlineDiffBytes"],
        max_evidence_calls=budgets["maxEvidenceCalls"],
        converge_at_calls=budgets["convergeAtCalls"],
        submit_by_turn=budgets["submitByTurn"],
    )


def _safe_exception_location(exception: Exception) -> str:
    frames = traceback.extract_tb(exception.__traceback__)
    if not frames:
        return "unknown"
    frame = frames[-1]
    return f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"


if __name__ == "__main__":
    raise SystemExit(main())
