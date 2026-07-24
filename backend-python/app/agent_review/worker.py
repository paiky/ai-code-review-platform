from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Event, Thread
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.agent_review_spike.runner import RunnerConfig, run_agent_candidate


WORKER_VERSION = "agent-worker-v1"
CLI_VERSION = "2.1.112"


def main() -> int:
    backend_url = _required_env("AGENT_REVIEW_BACKEND_URL").rstrip("/")
    token = _required_env("AGENT_REVIEW_WORKER_TOKEN")
    worker_id = os.getenv("AGENT_REVIEW_WORKER_ID", "agent-worker-1").strip()
    workspace_root = Path(os.getenv("AGENT_REVIEW_WORKSPACE_ROOT", "/workspaces")).resolve(strict=True)
    poll_seconds = max(float(os.getenv("AGENT_REVIEW_WORKER_POLL_SECONDS", "3")), 1.0)
    while True:
        try:
            _post(backend_url, token, "/internal/agent-review/workers/heartbeat", {
                "workerId": worker_id, "workerVersion": WORKER_VERSION, "cliVersion": CLI_VERSION,
            })
            claimed = _post(backend_url, token, "/internal/agent-review/jobs/claim", {"workerId": worker_id})
            job = claimed.get("data")
            if job:
                _run_job(backend_url, token, worker_id, workspace_root, job)
                continue
        except (OSError, ValueError, HTTPError, URLError):
            pass
        time.sleep(poll_seconds)


def _run_job(
    backend_url: str, token: str, worker_id: str, workspace_root: Path, job: dict[str, Any]
) -> None:
    if job.get("kind") == "CONFIG_TEST":
        _run_configuration_test(backend_url, token, worker_id, job)
        return
    job_id = int(job["jobId"])
    stop = Event()
    cancelled = Event()
    heartbeat = Thread(
        target=_heartbeat_loop,
        args=(backend_url, token, worker_id, job_id, stop, cancelled),
        daemon=True,
    )
    heartbeat.start()
    try:
        worktree = _resolve_worktree(workspace_root, str(job.get("worktree") or ""))
        budgets = job.get("budgets") or {}
        summary = run_agent_candidate(
            job.get("input") or {},
            worktree,
            str(job.get("apiKey") or ""),
            RunnerConfig(
                timeout_seconds=int(budgets.get("timeoutSeconds") or 600),
                max_turns=int(budgets.get("maxTurns") or 8),
                max_tool_calls=int(budgets.get("maxToolCalls") or 40),
                max_source_bytes=int(budgets.get("maxSourceBytes") or 200_000),
            ),
            cancel_event=cancelled,
        )
        base = {"workerId": worker_id, "idempotencyKey": job["idempotencyKey"], "runSummary": summary}
        if cancelled.is_set():
            _post(backend_url, token, f"/internal/agent-review/jobs/{job_id}/cancelled", base)
        elif summary.get("status") == "SUCCESS" and isinstance(summary.get("reviewCard"), dict):
            _post(backend_url, token, f"/internal/agent-review/jobs/{job_id}/complete", {**base, "reviewCard": summary["reviewCard"]})
        else:
            _post(backend_url, token, f"/internal/agent-review/jobs/{job_id}/fail", {
                **base,
                "failureCode": summary.get("errorCode") or "AGENT_RUN_FAILED",
                "failureMessage": "Agent Review did not produce a valid submitted Review Card",
            })
    except Exception as exception:
        _post(backend_url, token, f"/internal/agent-review/jobs/{job_id}/fail", {
            "workerId": worker_id,
            "idempotencyKey": job["idempotencyKey"],
            "failureCode": "AGENT_WORKER_ERROR",
            "failureMessage": str(exception)[:500],
            "runSummary": {},
        })
    finally:
        stop.set()
        heartbeat.join(timeout=2)


def _run_configuration_test(
    backend_url: str, token: str, worker_id: str, job: dict[str, Any]
) -> None:
    started = time.perf_counter()
    stop = Event()
    heartbeat = Thread(
        target=_worker_heartbeat_loop,
        args=(backend_url, token, worker_id, stop),
        daemon=True,
    )
    heartbeat.start()
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
    try:
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
    finally:
        stop.set()
        heartbeat.join(timeout=2)


def _worker_heartbeat_loop(backend_url: str, token: str, worker_id: str, stop: Event) -> None:
    while not stop.wait(15):
        try:
            _post(
                backend_url,
                token,
                "/internal/agent-review/workers/heartbeat",
                {"workerId": worker_id, "workerVersion": WORKER_VERSION, "cliVersion": CLI_VERSION},
            )
        except Exception:
            continue


def _heartbeat_loop(
    backend_url: str, token: str, worker_id: str, job_id: int, stop: Event, cancelled: Event
) -> None:
    while not stop.wait(15):
        try:
            response = _post(backend_url, token, f"/internal/agent-review/jobs/{job_id}/heartbeat", {"workerId": worker_id})
            if bool((response.get("data") or {}).get("cancelRequested")):
                cancelled.set()
        except Exception:
            continue


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


if __name__ == "__main__":
    raise SystemExit(main())
