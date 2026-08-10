from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import signal
import socket
import sys
from threading import Event, Lock, RLock, Thread
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
from app.agent_review_spike.anthropic_messages_runner import (
    AnthropicMessagesAgentRunner,
    AnthropicMessagesRunnerConfig,
    HttpxAnthropicMessagesTransport,
)
from app.agent_review_spike.chat_completions_runner import (
    ChatCompletionsRunnerConfig,
    HttpxChatCompletionsTransport,
    OpenAIChatCompletionsAgentRunner,
)
from app.agent_review_spike.responses_runner import (
    HttpxResponsesTransport,
    OpenAIResponsesAgentRunner,
    ResponsesRunnerConfig,
)
from app.agent_review_spike.runner import RunnerConfig, run_agent_candidate
WORKER_VERSION = "agent-worker-v1"
CLI_VERSION = "2.1.112"
DEFAULT_RUNTIME = "CLAUDE_CODE_DEEPSEEK"
CUSTOM_RUNTIME = "OPENAI_RESPONSES_CUSTOM"
CLAUDE_CODE_RUNNER = "CLAUDE_CODE"
OPENAI_RESPONSES_RUNNER = "OPENAI_RESPONSES_AGENT"
OPENAI_CHAT_RUNNER = "OPENAI_CHAT_AGENT"
ANTHROPIC_MESSAGES_RUNNER = "ANTHROPIC_MESSAGES_AGENT"
RESPONSES_RUNNER_VERSION = "openai-responses-agent-v1"
CHAT_COMPLETIONS_RUNNER_VERSION = "openai-chat-completions-agent-v1"
ANTHROPIC_MESSAGES_RUNNER_VERSION = "anthropic-messages-agent-v1"
WORKER_CAPABILITIES = [
    DEFAULT_RUNTIME,
    CLAUDE_CODE_RUNNER,
    CUSTOM_RUNTIME,
    OPENAI_RESPONSES_RUNNER,
    OPENAI_CHAT_RUNNER,
    ANTHROPIC_MESSAGES_RUNNER,
]
AGENT_WORKER_SHUTDOWN_GRACE_SECONDS = 930
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


class _WorkerActivityState:
    def __init__(self) -> None:
        self._lock = RLock()
        self._state = "IDLE"
        self._active_job_id: int | None = None
        self._active_run_id: int | None = None

    def begin(self, job: dict[str, Any]) -> None:
        with self._lock:
            if self._state != "DRAINING":
                self._state = "BUSY"
            self._active_job_id = (
                int(job["jobId"]) if job.get("jobId") is not None else None
            )
            self._active_run_id = (
                int(job["runId"]) if job.get("runId") is not None else None
            )

    def idle(self) -> None:
        with self._lock:
            if self._state != "DRAINING":
                self._state = "IDLE"
            self._active_job_id = None
            self._active_run_id = None

    def drain(self) -> None:
        with self._lock:
            self._state = "DRAINING"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            result: dict[str, Any] = {
                "state": self._state,
                "capacity": 1,
            }
            if self._active_job_id is not None:
                result["activeJobId"] = self._active_job_id
            if self._active_run_id is not None:
                result["activeRunId"] = self._active_run_id
            return result


class _DrainController:
    def __init__(
        self,
        activity: _WorkerActivityState,
        heartbeat_wakeup: Event,
    ) -> None:
        self._lock = RLock()
        self._requested = Event()
        self._activity = activity
        self._heartbeat_wakeup = heartbeat_wakeup

    def request(self) -> bool:
        with self._lock:
            if self._requested.is_set():
                return False
            self._activity.drain()
            self._requested.set()
            self._heartbeat_wakeup.set()
            return True

    def handle_signal(self, _signum, _frame) -> None:
        self.request()

    def is_requested(self) -> bool:
        return self._requested.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._requested.wait(timeout)


def main() -> int:
    backend_url = _required_env("AGENT_REVIEW_BACKEND_URL").rstrip("/")
    worker_id = _resolve_worker_id()
    arguments = sys.argv[1:]
    if arguments:
        if arguments != ["--healthcheck"]:
            raise ValueError("Only --healthcheck is supported")
        return _healthcheck(backend_url, worker_id)
    token = _required_env("AGENT_REVIEW_WORKER_TOKEN")
    workspace_root = Path(os.getenv("AGENT_REVIEW_WORKSPACE_ROOT", "/workspaces")).resolve(strict=True)
    poll_seconds = max(float(os.getenv("AGENT_REVIEW_WORKER_POLL_SECONDS", "3")), 1.0)
    process_stop = Event()
    heartbeat_wakeup = Event()
    activity = _WorkerActivityState()
    drain = _DrainController(activity, heartbeat_wakeup)
    signal.signal(signal.SIGTERM, drain.handle_signal)
    process_heartbeat = Thread(
        target=_worker_heartbeat_loop,
        args=(
            backend_url,
            token,
            worker_id,
            process_stop,
            activity,
            heartbeat_wakeup,
        ),
        daemon=True,
    )
    shutdown_watchdog = Thread(
        target=_shutdown_watchdog,
        args=(drain, process_stop),
        daemon=True,
    )
    process_heartbeat.start()
    shutdown_watchdog.start()
    try:
        return _worker_loop(
            backend_url,
            token,
            worker_id,
            workspace_root,
            poll_seconds,
            activity,
            drain,
        )
    except KeyboardInterrupt:
        return 0
    finally:
        process_stop.set()
        heartbeat_wakeup.set()
        process_heartbeat.join(timeout=2)


def _worker_loop(
    backend_url: str,
    token: str,
    worker_id: str,
    workspace_root: Path,
    poll_seconds: float,
    activity: _WorkerActivityState,
    drain: _DrainController,
) -> int:
    while not drain.is_requested():
        try:
            claimed = _post(
                backend_url,
                token,
                "/internal/agent-review/jobs/claim",
                {"workerId": worker_id},
            )
            job = claimed.get("data")
            if job:
                activity.begin(job)
                try:
                    _run_job(backend_url, token, worker_id, workspace_root, job)
                finally:
                    activity.idle()
                if drain.is_requested():
                    return 0
                continue
        except (OSError, ValueError, HTTPError, URLError):
            pass
        if drain.wait(poll_seconds):
            return 0
    return 0


def _shutdown_watchdog(
    drain: _DrainController,
    process_stop: Event,
    grace_seconds: float = AGENT_WORKER_SHUTDOWN_GRACE_SECONDS,
    force_exit=None,
) -> None:
    drain.wait()
    if process_stop.wait(max(float(grace_seconds), 0.0)):
        return
    (force_exit or os._exit)(0)


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
        worktree = _resolve_worktree(workspace_root, str(job.get("worktree") or ""))
        runtime = job.get("runtime") if isinstance(job.get("runtime"), dict) else {}
        runtime_type = str(runtime.get("runtimeType") or DEFAULT_RUNTIME).upper()
        runner_type = str(runtime.get("runnerType") or "").upper()
        if runner_type == ANTHROPIC_MESSAGES_RUNNER:
            endpoint = f"{str(runtime.get('baseUrl') or '').rstrip('/')}/messages"
            anthropic_result = AnthropicMessagesAgentRunner(
                HttpxAnthropicMessagesTransport(
                    endpoint,
                    str(runtime.get("apiKey") or ""),
                    verify_tls=_custom_tls_verify(runtime),
                ),
                _anthropic_runner_config_from_budgets(
                    job.get("budgets"),
                    model=str(runtime.get("model") or "synthetic-anthropic-model"),
                ),
            ).run(
                job.get("input") or {},
                worktree,
                cancel_event=cancelled,
                progress_callback=latest_audit.update,
            )
            summary = _normalize_anthropic_summary(anthropic_result)
        elif runner_type == OPENAI_CHAT_RUNNER:
            endpoint = f"{str(runtime.get('baseUrl') or '').rstrip('/')}/chat/completions"
            chat_result = OpenAIChatCompletionsAgentRunner(
                HttpxChatCompletionsTransport(
                    endpoint,
                    str(runtime.get("apiKey") or ""),
                    verify_tls=_custom_tls_verify(runtime),
                ),
                _chat_runner_config_from_budgets(
                    job.get("budgets"),
                    model=str(runtime.get("model") or "synthetic-chat-model"),
                ),
            ).run(
                job.get("input") or {},
                worktree,
                cancel_event=cancelled,
                progress_callback=latest_audit.update,
            )
            summary = _normalize_chat_summary(chat_result)
        elif runner_type == OPENAI_RESPONSES_RUNNER or runtime_type == CUSTOM_RUNTIME:
            endpoint = f"{str(runtime.get('baseUrl') or '').rstrip('/')}/responses"
            responses_result = OpenAIResponsesAgentRunner(
                HttpxResponsesTransport(
                    endpoint,
                    str(runtime.get("apiKey") or ""),
                    verify_tls=_custom_tls_verify(runtime),
                ),
                _responses_runner_config_from_budgets(
                    job.get("budgets"),
                    model=str(runtime.get("model") or "gpt-5.6-sol"),
                    reasoning_effort=str(runtime.get("reasoningEffort") or "high"),
                ),
            ).run(
                job.get("input") or {},
                worktree,
                cancel_event=cancelled,
                progress_callback=latest_audit.update,
            )
            summary = _normalize_responses_summary(responses_result)
        elif runner_type == CLAUDE_CODE_RUNNER or runtime_type == DEFAULT_RUNTIME:
            summary = run_agent_candidate(
                job.get("input") or {},
                worktree,
                str(runtime.get("apiKey") or job.get("apiKey") or ""),
                _runner_config_from_budgets(job.get("budgets"), runtime=runtime),
                cancel_event=cancelled,
                progress_callback=latest_audit.update,
            )
        else:
            raise ValueError("unsupported Agent runtime")
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
        runtime = job.get("runtime") if isinstance(job.get("runtime"), dict) else {}
        runtime_type = str(runtime.get("runtimeType") or DEFAULT_RUNTIME).upper()
        with tempfile.TemporaryDirectory(prefix="agent-config-test-") as temporary_name:
            worktree = Path(temporary_name)
            (worktree / "healthcheck.txt").write_text("agent_review_healthcheck=true\n", encoding="utf-8")
            synthetic_case = {
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
                }
            runner_type = str(runtime.get("runnerType") or "").upper()
            if runner_type == ANTHROPIC_MESSAGES_RUNNER:
                endpoint = f"{str(runtime.get('baseUrl') or '').rstrip('/')}/messages"
                summary = AnthropicMessagesAgentRunner(
                    HttpxAnthropicMessagesTransport(
                        endpoint,
                        str(runtime.get("apiKey") or ""),
                        verify_tls=_custom_tls_verify(runtime),
                    ),
                    _anthropic_runner_config_from_budgets(
                        budgets,
                        model=str(runtime.get("model") or "synthetic-anthropic-model"),
                    ),
                ).run(synthetic_case, worktree)
            elif runner_type == OPENAI_CHAT_RUNNER:
                endpoint = (
                    f"{str(runtime.get('baseUrl') or '').rstrip('/')}/chat/completions"
                )
                summary = OpenAIChatCompletionsAgentRunner(
                    HttpxChatCompletionsTransport(
                        endpoint,
                        str(runtime.get("apiKey") or ""),
                        verify_tls=_custom_tls_verify(runtime),
                    ),
                    _chat_runner_config_from_budgets(
                        budgets,
                        model=str(runtime.get("model") or "synthetic-chat-model"),
                    ),
                ).run(synthetic_case, worktree)
            elif runner_type == OPENAI_RESPONSES_RUNNER or runtime_type == CUSTOM_RUNTIME:
                endpoint = f"{str(runtime.get('baseUrl') or '').rstrip('/')}/responses"
                summary = OpenAIResponsesAgentRunner(
                    HttpxResponsesTransport(
                        endpoint,
                        str(runtime.get("apiKey") or ""),
                        verify_tls=_custom_tls_verify(runtime),
                    ),
                    _responses_runner_config_from_budgets(
                        budgets,
                        model=str(runtime.get("model") or "gpt-5.6-sol"),
                        reasoning_effort=str(runtime.get("reasoningEffort") or "high"),
                    ),
                ).run(synthetic_case, worktree)
            elif runner_type == CLAUDE_CODE_RUNNER or runtime_type == DEFAULT_RUNTIME:
                summary = run_agent_candidate(
                    synthetic_case,
                    worktree,
                    str(runtime.get("apiKey") or job.get("apiKey") or ""),
                    _runner_config_from_budgets(budgets, runtime=runtime),
                )
            else:
                raise ValueError("unsupported Agent runtime")
        status = "SUCCESS" if summary.get("status") == "SUCCESS" else "FAILED"
        if status == "SUCCESS":
            message = (
                "Anthropic Messages Agent + read-only tools connectivity succeeded"
                if runner_type == ANTHROPIC_MESSAGES_RUNNER
                else "OpenAI Chat Completions Agent + read-only tools connectivity succeeded"
                if runner_type == OPENAI_CHAT_RUNNER
                else "OpenAI Responses Agent + read-only tools connectivity succeeded"
                if runner_type == OPENAI_RESPONSES_RUNNER
                or runtime_type == CUSTOM_RUNTIME
                else "Claude Code + DeepSeek + read-only MCP connectivity succeeded"
            )
        else:
            message = str(summary.get("errorCode") or message)
    except Exception as exception:
        message = _failure_message(
            "AGENT_INVALID_BUDGET_CONFIG"
            if isinstance(exception, AgentBudgetValidationError)
            else "AGENT_WORKER_ERROR"
        )
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


def _worker_heartbeat_loop(
    backend_url: str,
    token: str,
    worker_id: str,
    stop: Event,
    activity: _WorkerActivityState,
    wake: Event | None = None,
) -> None:
    while True:
        try:
            _post(
                backend_url,
                token,
                "/internal/agent-review/workers/heartbeat",
                {
                    "workerId": worker_id,
                    "workerVersion": WORKER_VERSION,
                    "cliVersion": CLI_VERSION,
                    "capabilities": WORKER_CAPABILITIES,
                    "responsesRunnerVersion": RESPONSES_RUNNER_VERSION,
                    **activity.snapshot(),
                },
            )
        except Exception:
            pass
        if wake is None:
            if stop.wait(15):
                return
        else:
            wake.wait(15)
            wake.clear()
            if stop.is_set():
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


def _healthcheck(backend_url: str, worker_id: str) -> int:
    try:
        settings = _fetch_agent_settings(backend_url)
        pool = settings.get("workerPool")
        if not isinstance(pool, dict):
            return 1
        nodes = pool.get("nodes")
        if not isinstance(nodes, list):
            return 1
        matched = next(
            (
                node
                for node in nodes
                if isinstance(node, dict) and node.get("workerId") == worker_id
            ),
            None,
        )
    except Exception:
        return 1
    return 0 if matched and matched.get("online") is True else 1


def _fetch_agent_settings(backend_url: str) -> dict[str, Any]:
    request = Request(
        backend_url.rstrip("/") + "/api/code-quality-reviews/agent-settings",
        method="GET",
    )
    with urlopen(request, timeout=5) as response:
        value = json.loads(response.read().decode("utf-8"))
    data = value.get("data") if isinstance(value, dict) else None
    return data if isinstance(data, dict) else {}


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


def _runner_config_from_budgets(
    value: Any,
    *,
    runtime: dict[str, Any] | None = None,
) -> RunnerConfig:
    budgets = validate_agent_budgets(value)
    runtime = runtime or {}
    return RunnerConfig(
        timeout_seconds=budgets["timeoutSeconds"],
        max_turns=budgets["maxTurns"],
        max_tool_calls=budgets["maxToolCalls"],
        max_source_bytes=budgets["maxSourceBytes"],
        inline_diff_bytes=budgets["inlineDiffBytes"],
        max_evidence_calls=budgets["maxEvidenceCalls"],
        converge_at_calls=budgets["convergeAtCalls"],
        submit_by_turn=budgets["submitByTurn"],
        base_url=str(runtime.get("baseUrl") or "https://api.deepseek.com/anthropic"),
        model=str(runtime.get("model") or "deepseek-v4-pro[1m]"),
        reasoning_effort=str(runtime.get("reasoningEffort") or "high"),
        tls_verify=_custom_tls_verify(runtime),
    )


def _custom_tls_verify(runtime: dict[str, Any]) -> bool:
    """Only an explicit JSON false disables certificate verification."""
    return runtime.get("tlsVerify") is not False


def _responses_runner_config_from_budgets(
    value: Any,
    *,
    model: str,
    reasoning_effort: str,
) -> ResponsesRunnerConfig:
    return ResponsesRunnerConfig.from_budgets(
        validate_agent_budgets(value),
        model=model,
        reasoning_effort=reasoning_effort,
    )


def _chat_runner_config_from_budgets(
    value: Any,
    *,
    model: str,
) -> ChatCompletionsRunnerConfig:
    return ChatCompletionsRunnerConfig.from_budgets(
        validate_agent_budgets(value),
        model=model,
    )


def _anthropic_runner_config_from_budgets(
    value: Any,
    *,
    model: str,
) -> AnthropicMessagesRunnerConfig:
    return AnthropicMessagesRunnerConfig.from_budgets(
        validate_agent_budgets(value),
        model=model,
    )


def _normalize_responses_summary(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    card = result.pop("card", None)
    audit = result.pop("toolAudit", None)
    if isinstance(card, dict):
        result["reviewCard"] = card
    if isinstance(audit, dict):
        result["audit"] = audit
    result["runnerVersion"] = RESPONSES_RUNNER_VERSION
    result["cliVersion"] = None
    return result


def _normalize_chat_summary(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    card = result.pop("card", None)
    audit = result.pop("toolAudit", None)
    if isinstance(card, dict):
        result["reviewCard"] = card
    if isinstance(audit, dict):
        result["audit"] = audit
    result["runnerVersion"] = CHAT_COMPLETIONS_RUNNER_VERSION
    result["cliVersion"] = None
    return result


def _normalize_anthropic_summary(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    card = result.pop("card", None)
    audit = result.pop("toolAudit", None)
    if isinstance(card, dict):
        result["reviewCard"] = card
    if isinstance(audit, dict):
        result["audit"] = audit
    result["runnerVersion"] = ANTHROPIC_MESSAGES_RUNNER_VERSION
    result["cliVersion"] = None
    return result


def _safe_exception_location(exception: Exception) -> str:
    frames = traceback.extract_tb(exception.__traceback__)
    if not frames:
        return "unknown"
    frame = frames[-1]
    return f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"


if __name__ == "__main__":
    raise SystemExit(main())
