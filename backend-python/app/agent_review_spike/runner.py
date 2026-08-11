from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import tempfile
from time import perf_counter
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.agent_review_spike.budgets import AGENT_BUDGET_LIMITS
from app.agent_review_spike.metrics import (
    build_report_metrics,
    execution_summary,
    expected_outcome,
)
from app.agent_review_spike.prompting import (
    agent_system_prompt,
    baseline_system_prompt,
    review_input,
)
from app.agent_review_spike.schema import normalize_relative_path, validate_review_card


DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_ANTHROPIC_URL = "https://api.deepseek.com/anthropic"
AGENT_MODEL = "deepseek-v4-pro[1m]"
BASELINE_MODEL = AGENT_MODEL
MAX_CASES = 200
MAX_DIFF_CHARS = 2_000_000
MAX_CONTEXT_CHARS = 1_000_000


class SpikeRunError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class RunnerConfig:
    timeout_seconds: int = 600
    max_turns: int = 12
    max_tool_calls: int = 40
    max_source_bytes: int = 200_000
    inline_diff_bytes: int = 200_000
    max_evidence_calls: int = 10
    converge_at_calls: int = 8
    submit_by_turn: int = 9
    base_url: str = DEEPSEEK_ANTHROPIC_URL
    model: str = AGENT_MODEL
    reasoning_effort: str = "high"
    tls_verify: bool = True

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        hostname = str(parsed.hostname or "").casefold()
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.port not in {None, 443}
        ):
            raise ValueError("Claude Code base URL must be a safe HTTPS URL")
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise ValueError("Claude Code base URL must not use an IP address")
        if not self.model.strip() or len(self.model.strip()) > 128:
            raise ValueError("Claude Code model is invalid")
        if self.reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("Claude Code reasoning effort is invalid")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        workspace_root = Path(args.workspace_root).resolve(strict=True)
        manifest = _load_manifest(Path(args.manifest), workspace_root)
        cases = manifest["cases"]
        if args.case_id:
            cases = [case for case in cases if case["id"] == args.case_id]
            if not cases:
                raise SpikeRunError("CASE_NOT_FOUND", "requested case id does not exist")
        config = RunnerConfig(
            timeout_seconds=args.timeout_seconds,
            max_turns=args.max_turns,
            max_tool_calls=args.max_tool_calls,
            max_source_bytes=args.max_source_bytes,
        )
        output_path = Path(args.output)
        if args.validate_only:
            report = _validation_report(manifest, cases, workspace_root, config)
        else:
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise SpikeRunError("DEEPSEEK_API_KEY_MISSING", "DEEPSEEK_API_KEY is required")
            report = run_evaluation(
                manifest,
                cases,
                workspace_root,
                api_key,
                side=args.side,
                config=config,
            )
        _atomic_write_json(output_path, report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "sampleCount": len(cases),
                    "output": str(output_path),
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["status"] not in {"FAIL", "ERROR"} else 1
    except (OSError, ValueError, SpikeRunError) as exception:
        code = exception.code if isinstance(exception, SpikeRunError) else "INVALID_INPUT"
        print(json.dumps({"status": "ERROR", "errorCode": code}), file=sys.stderr)
        return 2


def run_evaluation(
    manifest: dict[str, Any],
    cases: list[dict[str, Any]],
    workspace_root: Path,
    api_key: str,
    *,
    side: str,
    config: RunnerConfig,
) -> dict[str, Any]:
    started_at = _now()
    results = []
    for case in cases:
        item: dict[str, Any] = {"caseId": case["id"]}
        if side in {"baseline", "both"}:
            item["baseline"] = _run_baseline(case, api_key, config)
        if side in {"candidate", "both"}:
            worktree = _resolve_worktree(workspace_root, case["worktree"])
            item["candidate"] = _run_candidate(case, worktree, api_key, config)
        results.append(item)

    attestations = manifest.get("sandboxAttestation") or {}
    metrics = (
        build_report_metrics(cases, results, attestations)
        if side == "both"
        else {"status": "PARTIAL_SIDE_ONLY", "sampleCount": len(cases)}
    )
    return {
        "schemaVersion": 1,
        "status": metrics["status"],
        "startedAt": started_at,
        "finishedAt": _now(),
        "runner": _runner_summary(config),
        "sandboxAttestation": {
            "readOnlyMount": bool(attestations.get("readOnlyMount")),
            "deepseekOnlyEgress": bool(attestations.get("deepseekOnlyEgress")),
        },
        "metrics": metrics,
        "cases": results,
        "retention": {
            "rawModelOutputSaved": False,
            "sourceSnippetsSaved": False,
            "reasoningSaved": False,
        },
    }


def _run_baseline(
    case: dict[str, Any], api_key: str, config: RunnerConfig
) -> dict[str, Any]:
    started = perf_counter()
    try:
        _assert_deepseek_url(DEEPSEEK_CHAT_URL)
        payload = {
            "model": BASELINE_MODEL,
            "messages": [
                {"role": "system", "content": baseline_system_prompt(case)},
                {"role": "user", "content": review_input(case)},
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
            "max_tokens": 16_000,
            "thinking": {"type": "enabled"},
            "reasoning_effort": "max",
        }
        request = Request(
            DEEPSEEK_CHAT_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ai-code-review-agent-spike/0.1",
            },
            method="POST",
        )
        with urlopen(request, timeout=config.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        card = validate_review_card(_parse_json_object(content), case["changedFiles"])
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        return execution_summary(
            case,
            status="SUCCESS",
            duration_ms=_duration_ms(started),
            card=card,
            session={"usage": _safe_usage(usage)},
        ) | {"usage": _safe_usage(usage)}
    except HTTPError as exception:
        return execution_summary(
            case,
            status="FAILED",
            duration_ms=_duration_ms(started),
            error_code=f"BASELINE_HTTP_{exception.code}",
        )
    except (URLError, TimeoutError):
        return execution_summary(
            case,
            status="FAILED",
            duration_ms=_duration_ms(started),
            error_code="BASELINE_NETWORK_ERROR",
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return execution_summary(
            case,
            status="FAILED",
            duration_ms=_duration_ms(started),
            error_code="BASELINE_OUTPUT_INVALID",
        )


def _run_candidate(
    case: dict[str, Any],
    worktree: Path,
    api_key: str,
    config: RunnerConfig,
    *,
    include_card: bool = False,
    cancel_event: Any = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    try:
        _assert_deepseek_url(DEEPSEEK_ANTHROPIC_URL)
        with tempfile.TemporaryDirectory(prefix="agent-review-") as temporary_name:
            temporary = Path(temporary_name)
            result_path = temporary / "review-card.json"
            audit_path = temporary / "tool-audit.json"
            mcp_path = temporary / "mcp.json"
            diff_map_path = temporary / "diff-map.json"
            home = temporary / "home"
            home.mkdir()
            diff_map_path.write_text(json.dumps(_split_diff_by_file(case), ensure_ascii=False), encoding="utf-8")
            mcp_environment = {
                "PYTHONPATH": os.environ.get("PYTHONPATH", "/opt/agent-review"),
                "REVIEW_WORKTREE_ROOT": str(worktree),
                "REVIEW_CHANGED_FILES_JSON": json.dumps(case["changedFiles"]),
                "REVIEW_RESULT_PATH": str(result_path),
                "REVIEW_AUDIT_PATH": str(audit_path),
                "REVIEW_MAX_TOOL_CALLS": str(config.max_tool_calls),
                "REVIEW_MAX_SOURCE_BYTES": str(config.max_source_bytes),
                "REVIEW_MAX_EVIDENCE_CALLS": str(config.max_evidence_calls),
                "REVIEW_CONVERGE_AT_CALLS": str(config.converge_at_calls),
                "REVIEW_DIFF_MAP_PATH": str(diff_map_path),
            }
            mcp_config = {
                "mcpServers": {
                    "review": {
                        "type": "stdio",
                        "command": sys.executable,
                        "args": ["-m", "app.agent_review_spike.mcp_server"],
                        "env": mcp_environment,
                    }
                }
            }
            mcp_path.write_text(json.dumps(mcp_config), encoding="utf-8")
            command = _claude_command(case, mcp_path, config)
            environment = _candidate_environment(api_key, home, config)
            progress_state: dict[str, Any] = {"sequence": -1, "phase": None}
            _notify_progress_callback(
                progress_callback,
                _sanitize_audit_snapshot({}),
                progress_state,
            )
            process = subprocess.Popen(
                command,
                cwd=worktree,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=True,
            )
            deadline = perf_counter() + config.timeout_seconds
            prompt_input: str | None = review_input(case)
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    _terminate_process_group(process)
                    audit = _load_safe_audit_snapshot(audit_path)
                    _notify_progress_callback(progress_callback, audit, progress_state)
                    return execution_summary(
                        case,
                        status="FAILED",
                        duration_ms=_duration_ms(started),
                        error_code="AGENT_CANCELLED",
                        audit=audit,
                    )
                audit = _load_safe_audit_snapshot(audit_path)
                if _audit_requests_schema_termination(audit):
                    _terminate_process_group(process)
                    _notify_progress_callback(progress_callback, audit, progress_state)
                    return execution_summary(
                        case,
                        status="FAILED",
                        duration_ms=_duration_ms(started),
                        error_code="AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED",
                        audit=audit,
                    )
                remaining = deadline - perf_counter()
                if remaining <= 0:
                    _terminate_process_group(process)
                    audit = _load_safe_audit_snapshot(audit_path)
                    _notify_progress_callback(progress_callback, audit, progress_state)
                    return execution_summary(
                        case,
                        status="FAILED",
                        duration_ms=_duration_ms(started),
                        error_code="AGENT_TIMEOUT",
                        audit=audit,
                    )
                try:
                    stdout, _stderr = process.communicate(
                        input=prompt_input, timeout=min(5.0, remaining)
                    )
                    break
                except subprocess.TimeoutExpired:
                    prompt_input = None
                    audit = _load_safe_audit_snapshot(audit_path)
                    _notify_progress_callback(progress_callback, audit, progress_state)
                    if cancel_event is not None and cancel_event.is_set():
                        _terminate_process_group(process)
                        return execution_summary(
                            case,
                            status="FAILED",
                            duration_ms=_duration_ms(started),
                            error_code="AGENT_CANCELLED",
                            audit=audit,
                        )
                    if _audit_requests_schema_termination(audit):
                        _terminate_process_group(process)
                        return execution_summary(
                            case,
                            status="FAILED",
                            duration_ms=_duration_ms(started),
                            error_code="AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED",
                            audit=audit,
                        )
            audit = _load_safe_audit_snapshot(audit_path)
            _notify_progress_callback(progress_callback, audit, progress_state)
            if cancel_event is not None and cancel_event.is_set():
                return execution_summary(
                    case,
                    status="FAILED",
                    duration_ms=_duration_ms(started),
                    error_code="AGENT_CANCELLED",
                    audit=audit,
                )
            if _audit_requests_schema_termination(audit):
                return execution_summary(
                    case,
                    status="FAILED",
                    duration_ms=_duration_ms(started),
                    error_code="AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED",
                    audit=audit,
                )
            session = _parse_claude_session(stdout)
            if process.returncode != 0:
                return execution_summary(
                    case,
                    status="FAILED",
                    duration_ms=_duration_ms(started),
                    error_code=_candidate_cli_failure_code(session, config.max_turns),
                    audit=audit,
                    session=session,
                )
            if not result_path.is_file():
                return execution_summary(
                    case,
                    status="FAILED",
                    duration_ms=_duration_ms(started),
                    error_code="AGENT_REVIEW_NOT_SUBMITTED",
                    audit=audit,
                    session=session,
                )
            card = validate_review_card(
                json.loads(result_path.read_text(encoding="utf-8")), case["changedFiles"]
            )
            summary = execution_summary(
                case,
                status="SUCCESS",
                duration_ms=_duration_ms(started),
                card=card,
                audit=audit,
                session=session,
            )
            summary["usage"] = session.get("usage") or {}
            if include_card:
                summary["reviewCard"] = card
            return summary
    except FileNotFoundError:
        return execution_summary(
            case,
            status="FAILED",
            duration_ms=_duration_ms(started),
            error_code="CLAUDE_CLI_NOT_FOUND",
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return execution_summary(
            case,
            status="FAILED",
            duration_ms=_duration_ms(started),
            error_code="AGENT_OUTPUT_INVALID",
        )


def _claude_command(
    case: dict[str, Any], mcp_path: Path, config: RunnerConfig
) -> list[str]:
    allowed = ",".join(
        [
            "mcp__review__list_files",
            "mcp__review__search_code",
            "mcp__review__read_file_range",
            "mcp__review__read_diff_range",
            "mcp__review__submit_review",
        ]
    )
    return [
        "claude",
        "-p",
        "--bare",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        str(config.max_turns),
        "--model",
        config.model,
        "--mcp-config",
        str(mcp_path),
        "--strict-mcp-config",
        "--tools",
        "",
        "--allowedTools",
        allowed,
        "--disallowedTools",
        "Bash,Read,Write,Edit,WebFetch,WebSearch,Task,NotebookEdit",
        "--permission-mode",
        "dontAsk",
        "--disable-slash-commands",
        "--no-chrome",
        "--no-session-persistence",
        "--append-system-prompt",
        agent_system_prompt(case, config.submit_by_turn),
    ]


def run_agent_candidate(
    case: dict[str, Any],
    worktree: Path,
    api_key: str,
    config: RunnerConfig | None = None,
    *,
    cancel_event: Any = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    effective_config = config or RunnerConfig()
    effective_budgets = {
        "maxTurns": effective_config.max_turns,
        "maxToolCalls": effective_config.max_tool_calls,
        "maxSourceBytes": effective_config.max_source_bytes,
        "timeoutSeconds": effective_config.timeout_seconds,
        "inlineDiffBytes": effective_config.inline_diff_bytes,
        "maxEvidenceCalls": effective_config.max_evidence_calls,
        "convergeAtCalls": effective_config.converge_at_calls,
        "submitByTurn": effective_config.submit_by_turn,
    }
    summary = _run_candidate(
        case,
        worktree,
        api_key,
        effective_config,
        include_card=True,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
    )
    summary["effectiveBudgets"] = effective_budgets
    return summary


def _split_diff_by_file(case: dict[str, Any]) -> dict[str, str]:
    changed = [str(item).replace("\\", "/") for item in case.get("changedFiles") or []]
    diff = str(case.get("diff") or "")
    result: dict[str, list[str]] = {path: [] for path in changed}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            candidate = line[6:].strip().replace("\\", "/")
            current = candidate if candidate in result else None
        if current is not None:
            result[current].append(line)
    if len(changed) == 1 and not result[changed[0]]:
        result[changed[0]] = diff.splitlines()
    return {path: "\n".join(lines) for path, lines in result.items()}


def _candidate_environment(
    api_key: str,
    home: Path,
    config: RunnerConfig | None = None,
) -> dict[str, str]:
    effective_config = config or RunnerConfig()
    result = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "CLAUDE_CONFIG_DIR": str(home / ".claude"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "ANTHROPIC_BASE_URL": effective_config.base_url.rstrip("/"),
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_MODEL": effective_config.model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": effective_config.model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": effective_config.model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": effective_config.model,
        "CLAUDE_CODE_EFFORT_LEVEL": effective_config.reasoning_effort,
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "DISABLE_BUG_COMMAND": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    if not effective_config.tls_verify:
        result["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
    for proxy_variable in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ):
        proxy_value = os.environ.get(proxy_variable)
        if proxy_value:
            result[proxy_variable] = proxy_value
    if os.name == "nt":
        result["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    return result


def _load_manifest(path: Path, workspace_root: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list):
        raise SpikeRunError("INVALID_MANIFEST", "manifest.cases must be an array")
    raw_cases = value["cases"]
    if not raw_cases or len(raw_cases) > MAX_CASES:
        raise SpikeRunError("INVALID_MANIFEST", f"manifest must contain 1 to {MAX_CASES} cases")
    cases = []
    seen = set()
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            raise SpikeRunError("INVALID_CASE", f"cases[{index}] must be an object")
        case = dict(raw_case)
        case_id = str(case.get("id") or "").strip()
        if not case_id or len(case_id) > 120 or case_id in seen:
            raise SpikeRunError("INVALID_CASE", f"cases[{index}].id is invalid or duplicated")
        seen.add(case_id)
        case["id"] = case_id
        case["worktree"] = normalize_relative_path(case.get("worktree"), "worktree")
        _resolve_worktree(workspace_root, case["worktree"])
        changed = case.get("changedFiles")
        if not isinstance(changed, list) or not changed:
            raise SpikeRunError("INVALID_CASE", f"cases[{index}].changedFiles is required")
        case["changedFiles"] = [
            normalize_relative_path(item, "changedFiles") for item in changed
        ]
        case["diff"] = _bounded_text(case.get("diff"), "diff", MAX_DIFF_CHARS)
        case["baselineContext"] = _bounded_optional_text(
            case.get("baselineContext"), "baselineContext", MAX_CONTEXT_CHARS
        )
        case["reviewInstructions"] = _bounded_optional_text(
            case.get("reviewInstructions"), "reviewInstructions", 20_000
        )
        if not isinstance(case.get("targetFinding"), dict):
            raise SpikeRunError("INVALID_CASE", f"cases[{index}].targetFinding is required")
        target = dict(case["targetFinding"])
        target["filePath"] = normalize_relative_path(
            target.get("filePath"), "targetFinding.filePath"
        )
        if target["filePath"] not in case["changedFiles"]:
            raise SpikeRunError(
                "INVALID_CASE", f"cases[{index}].targetFinding is outside changedFiles"
            )
        try:
            target_start = int(target.get("startLine") or 1)
            target_end = int(target.get("endLine") or target_start)
            target_tolerance = int(target.get("lineTolerance") or 5)
        except (TypeError, ValueError) as exception:
            raise SpikeRunError("INVALID_CASE", "targetFinding line values are invalid") from exception
        if target_start < 1 or target_end < target_start or not 0 <= target_tolerance <= 50:
            raise SpikeRunError("INVALID_CASE", "targetFinding line range is invalid")
        target["startLine"] = target_start
        target["endLine"] = target_end
        target["lineTolerance"] = target_tolerance
        keywords = target.get("titleKeywords") or []
        if not isinstance(keywords, list) or any(not isinstance(item, str) for item in keywords):
            raise SpikeRunError("INVALID_CASE", "targetFinding.titleKeywords must be an array")
        case["targetFinding"] = target
        try:
            expected_outcome(case)
        except ValueError as exception:
            raise SpikeRunError("INVALID_CASE", str(exception)) from exception
        cases.append(case)
    value["cases"] = cases
    attestations = value.get("sandboxAttestation")
    if attestations is not None and not isinstance(attestations, dict):
        raise SpikeRunError("INVALID_MANIFEST", "sandboxAttestation must be an object")
    return value


def _resolve_worktree(workspace_root: Path, relative: str) -> Path:
    current = workspace_root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise SpikeRunError("WORKTREE_SYMLINK_DENIED", "worktree path contains a symlink")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(workspace_root)
    except (FileNotFoundError, ValueError) as exception:
        raise SpikeRunError("WORKTREE_OUTSIDE_ROOT", "worktree is outside workspace root") from exception
    if not resolved.is_dir():
        raise SpikeRunError("WORKTREE_NOT_FOUND", "worktree is not a directory")
    return resolved


def _parse_claude_session(stdout: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "result":
            continue
        result = {
            "sessionId": event.get("session_id"),
            "numTurns": event.get("num_turns"),
            "usage": _safe_usage(event.get("usage") or {}),
            "resultSubtype": str(event.get("subtype") or "")[:80],
            "isError": bool(event.get("is_error")),
        }
    return result


def _candidate_cli_failure_code(session: dict[str, Any], max_turns: int) -> str:
    subtype = str(session.get("resultSubtype") or "").strip().upper().replace("-", "_")
    if subtype in {"ERROR_MAX_TURNS", "MAX_TURNS", "MAX_TURNS_EXCEEDED"}:
        return "AGENT_MAX_TURNS_EXCEEDED"
    try:
        turns = int(session.get("numTurns") or 0)
    except (TypeError, ValueError):
        turns = 0
    if turns >= max(int(max_turns), 1):
        return "AGENT_MAX_TURNS_EXCEEDED"
    return "AGENT_CLI_FAILED"


def _parse_json_object(value: Any) -> dict[str, Any]:
    text = str(value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("provider output must be an object")
    return parsed


def _safe_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        number = value.get(key)
        if isinstance(number, int) and number >= 0:
            result[key] = number
    return result


def _load_optional_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _load_safe_audit_snapshot(path: Path) -> dict[str, Any]:
    try:
        return _sanitize_audit_snapshot(_load_optional_object(path))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return _sanitize_audit_snapshot({})


def _sanitize_audit_snapshot(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    events: list[dict[str, Any]] = []
    raw_events = source.get("events") if isinstance(source.get("events"), list) else []
    for index, raw_event in enumerate(
        raw_events[: AGENT_BUDGET_LIMITS["maxToolCalls"]["max"]], 1
    ):
        if not isinstance(raw_event, dict):
            continue
        tool = str(raw_event.get("tool") or "")
        if tool not in {
            "list_files",
            "search_code",
            "read_file_range",
            "read_diff_range",
            "submit_review",
        }:
            continue
        sequence = _safe_sequence(raw_event.get("sequence"), index)
        if sequence is None:
            continue
        event = {
            "sequence": sequence,
            "tool": tool,
            "status": (
                str(raw_event.get("status") or "FAILED").upper()
                if str(raw_event.get("status") or "").upper() in {"SUCCESS", "FAILED"}
                else "FAILED"
            ),
            "durationMs": _bounded_non_negative(
                raw_event.get("durationMs"),
                AGENT_BUDGET_LIMITS["timeoutSeconds"]["max"] * 1_000,
            ),
            "itemCount": _bounded_non_negative(raw_event.get("itemCount"), 100_000),
            "sourceBytes": _bounded_non_negative(
                raw_event.get("sourceBytes"),
                AGENT_BUDGET_LIMITS["maxSourceBytes"]["max"],
            ),
            "pathSummary": _safe_path_summaries(raw_event.get("pathSummary"), 5),
            "reviewBudget": _safe_review_budget(raw_event.get("reviewBudget")),
        }
        error_code = str(raw_event.get("errorCode") or "")
        if error_code and error_code.replace("_", "").isalnum():
            event["errorCode"] = error_code[:80]
        if tool == "submit_review":
            event["attempt"] = _bounded_non_negative(raw_event.get("attempt"), 3)
            event["maxAttempts"] = 3
            event["violations"] = _safe_schema_failures(
                raw_event.get("violations")
            )
            event["violationCount"] = _bounded_non_negative(
                raw_event.get("violationCount"), 50
            )
            event["violationsTruncated"] = bool(
                raw_event.get("violationsTruncated")
            )
        query_hash = str(raw_event.get("queryHash") or "")
        if len(query_hash) == 16 and all(character in "0123456789abcdef" for character in query_hash):
            event["queryHash"] = query_hash
        events.append(event)
    events.sort(key=lambda item: item["sequence"])
    review_submitted = bool(source.get("reviewSubmitted"))
    review_budget = _safe_review_budget(source.get("reviewBudget"))
    phase = _audit_phase(events, review_submitted, review_budget)
    submit_attempt_count = _bounded_non_negative(source.get("submitAttemptCount"), 3)
    schema_failure_count = _bounded_non_negative(source.get("schemaFailureCount"), 3)
    output_repair_exhausted = bool(source.get("outputRepairExhausted"))
    output_termination_requested = bool(source.get("outputTerminationRequested"))
    last_schema_failures = _safe_schema_failures(source.get("lastSchemaFailures"))
    failure_chain: list[dict[str, Any]] = []
    if schema_failure_count:
        failure_chain.append(
            {"code": "REVIEW_SCHEMA_INVALID", "count": schema_failure_count}
        )
    if output_repair_exhausted:
        failure_chain.append(
            {"code": "AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED", "count": 1}
        )
    return {
        "phase": phase,
        "toolCallCount": _bounded_non_negative(
            source.get("toolCallCount"), AGENT_BUDGET_LIMITS["maxToolCalls"]["max"]
        ),
        "evidenceCallsUsed": _bounded_non_negative(
            source.get("evidenceCallsUsed"),
            AGENT_BUDGET_LIMITS["maxEvidenceCalls"]["max"],
        ),
        "sourceBytesReturned": _bounded_non_negative(
            source.get("sourceBytesReturned"),
            AGENT_BUDGET_LIMITS["maxSourceBytes"]["max"],
        ),
        "diffBytesReturned": _bounded_non_negative(
            source.get("diffBytesReturned"),
            AGENT_BUDGET_LIMITS["inlineDiffBytes"]["max"],
        ),
        "blockedAccessCount": _bounded_non_negative(
            source.get("blockedAccessCount"), AGENT_BUDGET_LIMITS["maxToolCalls"]["max"]
        ),
        "reviewSubmitted": review_submitted,
        "submitAttemptCount": submit_attempt_count,
        "schemaFailureCount": schema_failure_count,
        "lastSchemaFailures": last_schema_failures,
        "outputRepairExhausted": output_repair_exhausted,
        "outputTerminationRequested": output_termination_requested,
        "failureChain": failure_chain,
        "reviewBudget": review_budget,
        "topPathSummaries": _safe_path_summaries(source.get("topPathSummaries"), 20),
        "events": events,
    }


def _audit_requests_schema_termination(audit: dict[str, Any]) -> bool:
    return bool(
        audit.get("outputRepairExhausted")
        and audit.get("outputTerminationRequested")
    )


def _safe_schema_failures(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    allowed_reasons = {
        "REQUIRED",
        "TYPE",
        "ENUM",
        "UNSAFE_PATH",
        "PATH_OUTSIDE_CHANGED_FILES",
        "LINE_RANGE",
        "LENGTH",
        "CARD_SHAPE",
    }
    failures: list[dict[str, str]] = []
    for raw in value[:5]:
        if not isinstance(raw, dict):
            continue
        reason_code = str(raw.get("reasonCode") or "")
        field = str(raw.get("field") or "")[:120]
        if reason_code not in allowed_reasons or not re.fullmatch(
            r"\$|[A-Za-z][A-Za-z0-9]*(?:\[\d+\]|\.[A-Za-z][A-Za-z0-9]*)*",
            field,
        ):
            continue
        failures.append({"reasonCode": reason_code, "field": field})
    return failures


def _notify_progress_callback(
    callback: Callable[[dict[str, Any]], None] | None,
    snapshot: dict[str, Any],
    state: dict[str, Any],
) -> None:
    if callback is None:
        return
    events = snapshot.get("events") if isinstance(snapshot.get("events"), list) else []
    sequence = max(
        (int(event.get("sequence") or 0) for event in events if isinstance(event, dict)),
        default=0,
    )
    phase = str(snapshot.get("phase") or "ANALYZING")
    if sequence <= int(state.get("sequence") or 0) and phase == state.get("phase"):
        return
    state["sequence"] = sequence
    state["phase"] = phase
    try:
        callback(snapshot)
    except Exception:
        # 可观测性回调不能改变 Claude CLI 的主结果。
        return


def _safe_review_budget(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    phase = str(source.get("phase") or "DISCOVERY").upper()
    if phase not in {"DISCOVERY", "CONVERGE", "SUBMIT"}:
        phase = "DISCOVERY"
    return {
        "phase": phase,
        "evidenceCallsUsed": _bounded_non_negative(
            source.get("evidenceCallsUsed"),
            AGENT_BUDGET_LIMITS["maxEvidenceCalls"]["max"],
        ),
        "evidenceCallsRemaining": _bounded_non_negative(
            source.get("evidenceCallsRemaining"),
            AGENT_BUDGET_LIMITS["maxEvidenceCalls"]["max"],
        ),
        "sourceBytesRemaining": _bounded_non_negative(
            source.get("sourceBytesRemaining"),
            AGENT_BUDGET_LIMITS["maxSourceBytes"]["max"],
        ),
        "mustSubmit": bool(source.get("mustSubmit")) or phase == "SUBMIT",
    }


def _safe_path_summaries(value: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    summaries: list[dict[str, Any]] = []
    for raw in value[:limit]:
        if not isinstance(raw, dict):
            continue
        path_hash = str(raw.get("pathHash") or "")
        suffix = str(raw.get("suffix") or "").casefold()
        if len(path_hash) != 16 or not all(
            character in "0123456789abcdef" for character in path_hash
        ):
            continue
        if len(suffix) > 20 or any(character not in ".abcdefghijklmnopqrstuvwxyz0123456789" for character in suffix):
            suffix = ""
        summaries.append(
            {
                "pathHash": path_hash,
                "suffix": suffix,
                "depth": _bounded_non_negative(raw.get("depth"), 100),
            }
        )
    return summaries


def _audit_phase(
    events: list[dict[str, Any]],
    review_submitted: bool,
    review_budget: dict[str, Any],
) -> str:
    if review_submitted or (events and events[-1].get("tool") == "submit_review"):
        return "SUBMITTING"
    if review_budget.get("phase") == "SUBMIT":
        return "SUBMITTING"
    if review_budget.get("phase") == "CONVERGE":
        return "CONVERGING"
    return "TOOL_ACTIVITY" if events else "ANALYZING"


def _bounded_non_negative(value: Any, maximum: int) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return min(max(int(value or 0), 0), maximum)
    except (TypeError, ValueError):
        return 0


def _safe_sequence(value: Any, fallback: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        sequence = int(value if value is not None else fallback)
    except (TypeError, ValueError):
        return None
    return (
        sequence
        if 1 <= sequence <= AGENT_BUDGET_LIMITS["maxToolCalls"]["max"]
        else None
    )


def _validation_report(
    manifest: dict[str, Any],
    cases: list[dict[str, Any]],
    workspace_root: Path,
    config: RunnerConfig,
) -> dict[str, Any]:
    attestations = manifest.get("sandboxAttestation") or {}
    return {
        "schemaVersion": 1,
        "status": "VALIDATED",
        "finishedAt": _now(),
        "runner": _runner_summary(config),
        "sampleCount": len(cases),
        "worktreeCount": len({_resolve_worktree(workspace_root, case["worktree"]) for case in cases}),
        "sandboxAttestation": {
            "readOnlyMount": bool(attestations.get("readOnlyMount")),
            "deepseekOnlyEgress": bool(attestations.get("deepseekOnlyEgress")),
        },
        "retention": {
            "rawModelOutputSaved": False,
            "sourceSnippetsSaved": False,
            "reasoningSaved": False,
        },
    }


def _runner_summary(config: RunnerConfig) -> dict[str, Any]:
    return {
        "baselineModel": BASELINE_MODEL,
        "candidateModel": AGENT_MODEL,
        "maxTurns": config.max_turns,
        "maxToolCalls": config.max_tool_calls,
        "maxSourceBytes": config.max_source_bytes,
        "timeoutSeconds": config.timeout_seconds,
        "inlineDiffBytes": config.inline_diff_bytes,
        "maxEvidenceCalls": config.max_evidence_calls,
        "convergeAtCalls": config.converge_at_calls,
        "submitByTurn": config.submit_by_turn,
        "reasoningEffort": "high",
        "builtInToolsEnabled": False,
        "allowedMcpTools": [
            "list_files",
            "search_code",
            "read_file_range",
            "read_diff_range",
            "submit_review",
        ],
    }


def _assert_deepseek_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "api.deepseek.com":
        raise SpikeRunError("EGRESS_TARGET_DENIED", "only the DeepSeek API endpoint is allowed")


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass


def _bounded_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpikeRunError("INVALID_CASE", f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise SpikeRunError("INVALID_CASE", f"{field} exceeds the maximum length")
    return value


def _bounded_optional_text(value: Any, field: str, maximum: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > maximum:
        raise SpikeRunError("INVALID_CASE", f"{field} is invalid")
    return value


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=f".{path.name}."
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _duration_ms(started: float) -> int:
    return max(int((perf_counter() - started) * 1000), 0)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the phase-1 read-only Agent Review spike")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--side", choices=["baseline", "candidate", "both"], default="both")
    parser.add_argument("--case-id")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, choices=range(1, 601), default=600)
    parser.add_argument("--max-turns", type=int, choices=range(1, 13), default=12)
    parser.add_argument("--max-tool-calls", type=int, choices=range(1, 41), default=40)
    parser.add_argument(
        "--max-source-bytes", type=int, choices=range(1, 200_001), default=200_000
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
