from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from time import monotonic, perf_counter, sleep
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlparse

import httpx

from app.agent_review_spike.budgets import DEFAULT_AGENT_BUDGETS, validate_agent_budgets
from app.agent_review_spike.prompting import agent_system_prompt, review_input
from app.agent_review_spike.tool_executor import ReviewToolExecutor, tool_definitions
from app.agent_review_spike.workspace import ReviewWorkspace, ToolBudget


ALLOWED_TOOL_NAMES = frozenset(item["name"] for item in tool_definitions())
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
SAFE_ERROR_MESSAGES = {
    "AGENT_CUSTOM_CONFIG_INCOMPLETE": "自定义 Agent 配置不完整",
    "AGENT_ANTHROPIC_MESSAGES_UNSUPPORTED": "中转站不支持 Anthropic Messages 协议",
    "AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID": "中转站返回的 Anthropic Messages 协议结构无效",
    "AGENT_CUSTOM_AUTH_FAILED": "中转站认证失败",
    "AGENT_CUSTOM_MODEL_UNAVAILABLE": "中转站不支持当前模型",
    "AGENT_CUSTOM_RATE_LIMITED": "中转站请求频率受限",
    "AGENT_CUSTOM_NETWORK_ERROR": "中转站网络请求失败",
    "AGENT_CUSTOM_TOOL_CALL_INVALID": "中转站返回了无效工具调用",
    "AGENT_CANCELLED": "Agent Review 已取消",
    "AGENT_TIMEOUT": "Agent Review 执行超时",
    "AGENT_MAX_TURNS_EXCEEDED": "Agent Review 已达到最大决策回合数",
    "AGENT_SUBMIT_DEADLINE_EXCEEDED": "Agent Review 未在规定回合进入提交阶段",
    "AGENT_REVIEW_NOT_SUBMITTED": "Agent Review 未调用 submit_review",
    "AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED": "Review Card 结构修正已达到安全上限",
}


class AnthropicMessagesAgentError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(SAFE_ERROR_MESSAGES.get(code, "Agent Review 执行失败"))


class AnthropicMessagesTransportError(RuntimeError):
    def __init__(self, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__("Anthropic Messages transport failed")


class AnthropicMessagesTransport(Protocol):
    def create(self, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]: ...


class HttpxAnthropicMessagesTransport:
    """Messages HTTP adapter that discards provider error bodies by design."""

    def __init__(self, endpoint_url: str, api_key: str, *, verify_tls: bool = True) -> None:
        if not endpoint_url.strip() or not api_key.strip() or not isinstance(verify_tls, bool):
            raise AnthropicMessagesAgentError("AGENT_CUSTOM_CONFIG_INCOMPLETE")
        parsed = urlparse(endpoint_url.strip())
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.path.rstrip("/").endswith("/messages")
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise AnthropicMessagesAgentError("AGENT_CUSTOM_CONFIG_INCOMPLETE")
        self.endpoint_url = endpoint_url.strip()
        self.api_key = api_key
        self.verify_tls = verify_tls

    def create(self, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        try:
            response = httpx.post(
                self.endpoint_url,
                json=payload,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                    "user-agent": "ai-code-review-anthropic-messages-agent/0.1",
                },
                timeout=max(float(timeout_seconds), 0.001),
                verify=self.verify_tls,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exception:
            raise AnthropicMessagesTransportError() from exception
        if response.status_code >= 400:
            raise AnthropicMessagesTransportError(status_code=response.status_code)
        try:
            value = response.json()
        except (TypeError, ValueError) as exception:
            raise AnthropicMessagesAgentError(
                "AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID"
            ) from exception
        if not isinstance(value, dict):
            raise AnthropicMessagesAgentError(
                "AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID"
            )
        return value


@dataclass(frozen=True)
class AnthropicMessagesRunnerConfig:
    model: str = "synthetic-anthropic-model"
    max_output_tokens: int = 4096
    max_turns: int = DEFAULT_AGENT_BUDGETS["maxTurns"]
    max_tool_calls: int = DEFAULT_AGENT_BUDGETS["maxToolCalls"]
    max_source_bytes: int = DEFAULT_AGENT_BUDGETS["maxSourceBytes"]
    timeout_seconds: int = DEFAULT_AGENT_BUDGETS["timeoutSeconds"]
    inline_diff_bytes: int = DEFAULT_AGENT_BUDGETS["inlineDiffBytes"]
    max_evidence_calls: int = DEFAULT_AGENT_BUDGETS["maxEvidenceCalls"]
    converge_at_calls: int = DEFAULT_AGENT_BUDGETS["convergeAtCalls"]
    submit_by_turn: int = DEFAULT_AGENT_BUDGETS["submitByTurn"]
    max_retries: int = 2

    def __post_init__(self) -> None:
        validate_agent_budgets(self.effective_budgets())
        if (
            not self.model.strip()
            or not 256 <= self.max_output_tokens <= 8192
            or not 0 <= self.max_retries <= 3
        ):
            raise AnthropicMessagesAgentError("AGENT_CUSTOM_CONFIG_INCOMPLETE")

    @classmethod
    def from_budgets(
        cls,
        budgets: Mapping[str, int],
        *,
        model: str = "synthetic-anthropic-model",
        max_output_tokens: int = 4096,
        max_retries: int = 2,
    ) -> AnthropicMessagesRunnerConfig:
        validated = validate_agent_budgets(dict(budgets))
        return cls(
            model=model.strip(),
            max_output_tokens=max_output_tokens,
            max_turns=validated["maxTurns"],
            max_tool_calls=validated["maxToolCalls"],
            max_source_bytes=validated["maxSourceBytes"],
            timeout_seconds=validated["timeoutSeconds"],
            inline_diff_bytes=validated["inlineDiffBytes"],
            max_evidence_calls=validated["maxEvidenceCalls"],
            converge_at_calls=validated["convergeAtCalls"],
            submit_by_turn=validated["submitByTurn"],
            max_retries=min(max(int(max_retries), 0), 3),
        )

    def effective_budgets(self) -> dict[str, int]:
        return {
            "maxTurns": self.max_turns,
            "maxToolCalls": self.max_tool_calls,
            "maxSourceBytes": self.max_source_bytes,
            "timeoutSeconds": self.timeout_seconds,
            "inlineDiffBytes": self.inline_diff_bytes,
            "maxEvidenceCalls": self.max_evidence_calls,
            "convergeAtCalls": self.converge_at_calls,
            "submitByTurn": self.submit_by_turn,
        }


class AnthropicMessagesAgentRunner:
    def __init__(
        self,
        transport: AnthropicMessagesTransport,
        config: AnthropicMessagesRunnerConfig | None = None,
        *,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.transport = transport
        self.config = config or AnthropicMessagesRunnerConfig.from_budgets(
            DEFAULT_AGENT_BUDGETS
        )
        self.clock = clock
        self.sleeper = sleeper

    def run(
        self,
        case: dict[str, Any],
        worktree: Path,
        *,
        cancel_event: Any = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        usage: dict[str, int] = {}
        turn_count = 0
        audit: dict[str, Any] = {}
        try:
            self._validate_case(case)
            effective_case = dict(case)
            if len(str(case.get("diff") or "").encode("utf-8")) > self.config.inline_diff_bytes:
                effective_case["diffMode"] = "TOOL_PAGED"
            deadline = self.clock() + self.config.timeout_seconds
            with tempfile.TemporaryDirectory(prefix="anthropic-messages-agent-review-") as name:
                temporary = Path(name)
                result_path = temporary / "review-card.json"
                executor = ReviewToolExecutor(
                    ReviewWorkspace(worktree),
                    [str(item).replace("\\", "/") for item in effective_case["changedFiles"]],
                    result_path,
                    temporary / "tool-audit.json",
                    ToolBudget(
                        max_calls=self.config.max_tool_calls,
                        max_source_bytes=self.config.max_source_bytes,
                        max_evidence_calls=self.config.max_evidence_calls,
                        converge_at_evidence_calls=self.config.converge_at_calls,
                    ),
                    _split_diff_by_file(effective_case),
                )
                messages: list[dict[str, Any]] = [
                    {"role": "user", "content": review_input(effective_case)}
                ]
                seen_call_ids: set[str] = set()
                while turn_count < self.config.max_turns:
                    self._check_control(cancel_event, deadline)
                    response = self._request_with_retry(
                        self._request_payload(effective_case, messages),
                        cancel_event,
                        deadline,
                    )
                    turn_count += 1
                    _merge_usage(usage, response.get("usage"))
                    assistant, calls = _validate_response(response)
                    messages.append(assistant)
                    if turn_count >= self.config.submit_by_turn and any(
                        call["name"] != "submit_review" for call in calls
                    ):
                        raise AnthropicMessagesAgentError(
                            "AGENT_SUBMIT_DEADLINE_EXCEEDED"
                        )
                    if any(call["name"] == "submit_review" for call in calls[:-1]):
                        raise AnthropicMessagesAgentError(
                            "AGENT_CUSTOM_TOOL_CALL_INVALID"
                        )
                    tool_results: list[dict[str, Any]] = []
                    for call in calls:
                        self._check_control(cancel_event, deadline)
                        call_id = _required_call_id(call, seen_call_ids)
                        tool_name = call["name"]
                        if tool_name not in ALLOWED_TOOL_NAMES:
                            raise AnthropicMessagesAgentError(
                                "AGENT_CUSTOM_TOOL_CALL_INVALID"
                            )
                        result = executor.execute(tool_name, call["input"])
                        audit = executor.audit_summary()
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": call_id,
                                "content": json.dumps(
                                    result.value,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                                "is_error": result.is_error,
                            }
                        )
                        self._notify_progress(progress_callback, executor)
                        if cancel_event is not None and cancel_event.is_set():
                            raise AnthropicMessagesAgentError("AGENT_CANCELLED")
                        if executor.output_repair_exhausted:
                            raise AnthropicMessagesAgentError(
                                "AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED"
                            )
                        if executor.submitted:
                            return _safe_summary(
                                status="SUCCESS",
                                started=started,
                                turn_count=turn_count,
                                usage=usage,
                                audit=audit,
                                budgets=self.config.effective_budgets(),
                                card=json.loads(result_path.read_text(encoding="utf-8")),
                            )
                    messages.append({"role": "user", "content": tool_results})
                raise AnthropicMessagesAgentError("AGENT_MAX_TURNS_EXCEEDED")
        except AnthropicMessagesAgentError as exception:
            return _safe_summary(
                status="FAILED",
                started=started,
                turn_count=turn_count,
                usage=usage,
                audit=audit,
                budgets=self.config.effective_budgets(),
                error_code=exception.code,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return _safe_summary(
                status="FAILED",
                started=started,
                turn_count=turn_count,
                usage=usage,
                audit=audit,
                budgets=self.config.effective_budgets(),
                error_code="AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID",
            )

    def _request_payload(
        self, case: dict[str, Any], messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "model": self.config.model,
            "max_tokens": self.config.max_output_tokens,
            "system": agent_system_prompt(case, self.config.submit_by_turn),
            "messages": messages,
            "tools": [
                {
                    "name": item["name"],
                    "description": item["description"],
                    "input_schema": item["inputSchema"],
                }
                for item in tool_definitions()
            ],
            "tool_choice": {"type": "any"},
        }

    def _request_with_retry(
        self, payload: dict[str, Any], cancel_event: Any, deadline: float
    ) -> dict[str, Any]:
        attempts = 0
        while True:
            self._check_control(cancel_event, deadline)
            try:
                return self.transport.create(
                    payload, max(deadline - self.clock(), 0.001)
                )
            except AnthropicMessagesAgentError:
                raise
            except AnthropicMessagesTransportError as exception:
                status = exception.status_code
                if status in RETRYABLE_STATUS_CODES and attempts < self.config.max_retries:
                    attempts += 1
                    delay = min(
                        0.1 * (2 ** (attempts - 1)),
                        max(deadline - self.clock(), 0.0),
                    )
                    if delay <= 0:
                        raise AnthropicMessagesAgentError("AGENT_TIMEOUT") from exception
                    self.sleeper(delay)
                    continue
                raise AnthropicMessagesAgentError(
                    _transport_error_code(status)
                ) from exception
            except Exception as exception:
                raise AnthropicMessagesAgentError(
                    "AGENT_CUSTOM_NETWORK_ERROR"
                ) from exception

    def _check_control(self, cancel_event: Any, deadline: float) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise AnthropicMessagesAgentError("AGENT_CANCELLED")
        if self.clock() >= deadline:
            raise AnthropicMessagesAgentError("AGENT_TIMEOUT")

    @staticmethod
    def _validate_case(case: Any) -> None:
        if not isinstance(case, dict) or not str(case.get("id") or "").strip():
            raise AnthropicMessagesAgentError(
                "AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID"
            )
        changed_files = case.get("changedFiles")
        if not isinstance(changed_files, list) or not changed_files:
            raise AnthropicMessagesAgentError(
                "AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID"
            )

    @staticmethod
    def _notify_progress(
        callback: Callable[[dict[str, Any]], None] | None,
        executor: ReviewToolExecutor,
    ) -> None:
        if callback is None:
            return
        try:
            callback(executor.audit_summary())
        except Exception:
            return


def _validate_response(response: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if (
        not isinstance(response, dict)
        or response.get("type") != "message"
        or response.get("role") != "assistant"
        or response.get("stop_reason") != "tool_use"
        or not isinstance(response.get("id"), str)
        or not response["id"].strip()
    ):
        raise AnthropicMessagesAgentError(
            "AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID"
        )
    content = response.get("content")
    if not isinstance(content, list):
        raise AnthropicMessagesAgentError(
            "AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID"
        )
    safe_content: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            raise AnthropicMessagesAgentError("AGENT_CUSTOM_TOOL_CALL_INVALID")
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            safe_content.append({"type": "text", "text": block["text"]})
            continue
        if block.get("type") != "tool_use":
            raise AnthropicMessagesAgentError("AGENT_CUSTOM_TOOL_CALL_INVALID")
        if (
            not isinstance(block.get("name"), str)
            or not isinstance(block.get("input"), dict)
        ):
            raise AnthropicMessagesAgentError("AGENT_CUSTOM_TOOL_CALL_INVALID")
        safe_call = {
            "type": "tool_use",
            "id": block.get("id"),
            "name": block["name"],
            "input": block["input"],
        }
        safe_content.append(safe_call)
        calls.append(safe_call)
    if not calls:
        raise AnthropicMessagesAgentError("AGENT_REVIEW_NOT_SUBMITTED")
    return {"role": "assistant", "content": safe_content}, calls


def _required_call_id(call: dict[str, Any], seen: set[str]) -> str:
    call_id = str(call.get("id") or "").strip()
    if not call_id or len(call_id) > 200 or call_id in seen:
        raise AnthropicMessagesAgentError("AGENT_CUSTOM_TOOL_CALL_INVALID")
    seen.add(call_id)
    return call_id


def _transport_error_code(status_code: int | None) -> str:
    if status_code in {401, 403}:
        return "AGENT_CUSTOM_AUTH_FAILED"
    if status_code == 404:
        return "AGENT_ANTHROPIC_MESSAGES_UNSUPPORTED"
    if status_code in {400, 409, 422}:
        return "AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID"
    if status_code == 429:
        return "AGENT_CUSTOM_RATE_LIMITED"
    return "AGENT_CUSTOM_NETWORK_ERROR"


def _merge_usage(target: dict[str, int], value: Any) -> None:
    if not isinstance(value, dict):
        return
    for source, destination in (
        ("input_tokens", "input_tokens"),
        ("output_tokens", "output_tokens"),
    ):
        number = value.get(source)
        if isinstance(number, int) and not isinstance(number, bool) and number >= 0:
            target[destination] = target.get(destination, 0) + number
    target["total_tokens"] = target.get("input_tokens", 0) + target.get(
        "output_tokens", 0
    )


def _split_diff_by_file(case: dict[str, Any]) -> dict[str, str]:
    changed = [str(item).replace("\\", "/") for item in case.get("changedFiles") or []]
    result: dict[str, list[str]] = {path: [] for path in changed}
    current: str | None = None
    for line in str(case.get("diff") or "").splitlines():
        if line.startswith("+++ b/"):
            candidate = line[6:].strip().replace("\\", "/")
            current = candidate if candidate in result else None
        if current is not None:
            result[current].append(line)
    if len(changed) == 1 and not result[changed[0]]:
        result[changed[0]] = str(case.get("diff") or "").splitlines()
    return {path: "\n".join(lines) for path, lines in result.items()}


def _safe_summary(
    *,
    status: str,
    started: float,
    turn_count: int,
    usage: dict[str, int],
    audit: dict[str, Any],
    budgets: dict[str, int],
    card: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "durationMs": max(int((perf_counter() - started) * 1000), 0),
        "session": {"turnCount": max(int(turn_count), 0), "usage": dict(usage)},
        "toolAudit": audit,
        "effectiveBudgets": budgets,
        "retention": {
            "rawResponseSaved": False,
            "reasoningSaved": False,
            "sourceSnippetsSaved": False,
            "toolArgumentsSaved": False,
        },
    }
    if card is not None:
        result["card"] = card
    if error_code:
        result["errorCode"] = error_code
        result["message"] = SAFE_ERROR_MESSAGES[error_code]
    return result
