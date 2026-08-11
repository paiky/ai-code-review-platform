from __future__ import annotations

from copy import deepcopy
import json
from threading import Event
from typing import Any

import httpx
import pytest

from app.agent_review_spike.budgets import DEFAULT_AGENT_BUDGETS
from app.agent_review_spike.chat_completions_runner import (
    ChatCompletionsAgentError,
    ChatCompletionsRunnerConfig,
    ChatCompletionsTransportError,
    HttpxChatCompletionsTransport,
    OpenAIChatCompletionsAgentRunner,
)
from app.agent_review_spike.synthetic_chat_completions_validation import (
    run_synthetic_validation,
)


class ScriptedTransport:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.payloads: list[dict[str, Any]] = []

    def create(self, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        del timeout_seconds
        self.payloads.append(deepcopy(payload))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def worktree(tmp_path):
    source = tmp_path / "src" / "service.py"
    source.parent.mkdir(parents=True)
    source.write_text("UNIQUE_CHAT_SOURCE_SECRET\nsecond line\n", encoding="utf-8")
    return tmp_path


def _case() -> dict[str, Any]:
    return {
        "id": "chat-unit",
        "title": "Chat Completions unit test",
        "changedFiles": ["src/service.py"],
        "diff": "+++ b/src/service.py\n@@ -1 +1 @@\n-old\n+UNIQUE_CHAT_DIFF_SECRET",
        "baselineContext": "bounded synthetic context",
    }


def _card() -> dict[str, Any]:
    return {"summary": "未发现问题", "overallLevel": "LOW", "findings": []}


def _call(call_id: str, name: str, arguments: Any) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
        },
    }


def _response(turn: int, *calls: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{turn}",
        "object": "chat.completion",
        "choices": [{
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {"role": "assistant", "content": None, "tool_calls": list(calls)},
        }],
        "usage": {
            "prompt_tokens": turn,
            "completion_tokens": 2,
            "total_tokens": turn + 2,
            "unsafe_detail": "must-not-be-retained",
        },
    }


def test_chat_runner_continues_parallel_tool_calls_and_submits_structured_review(worktree):
    transport = ScriptedTransport([
        _response(
            1,
            _call("call-1", "read_diff_range", {
                "path": "src/service.py", "startLine": 1, "endLine": 3
            }),
            _call("call-2", "read_file_range", {
                "path": "src/service.py", "startLine": 1, "endLine": 2
            }),
        ),
        _response(2, _call("call-3", "submit_review", _card())),
    ])

    result = OpenAIChatCompletionsAgentRunner(transport).run(_case(), worktree)

    assert result["status"] == "SUCCESS"
    assert result["card"] == _card()
    assert result["session"] == {
        "turnCount": 2,
        "usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
    }
    assert result["toolAudit"]["toolCallCount"] == 3
    assert result["toolAudit"]["reviewSubmitted"] is True
    first = transport.payloads[0]
    assert first["parallel_tool_calls"] is False
    assert first["tool_choice"] == "required"
    assert {item["function"]["name"] for item in first["tools"]} == {
        "list_files", "search_code", "read_file_range", "read_diff_range", "submit_review"
    }
    continued = transport.payloads[1]["messages"]
    assert continued[-3]["role"] == "assistant"
    assert [item["tool_call_id"] for item in continued[-2:]] == ["call-1", "call-2"]
    safe_text = json.dumps(result, ensure_ascii=False)
    assert "UNIQUE_CHAT_SOURCE_SECRET" not in safe_text
    assert "UNIQUE_CHAT_DIFF_SECRET" not in safe_text
    assert "src/service.py" not in safe_text
    assert "unsafe_detail" not in safe_text


@pytest.mark.parametrize(
    "bad_response",
    [
        {"object": "chat.completion", "id": "bad", "choices": []},
        {
            "object": "chat.completion", "id": "bad", "choices": [{
                "finish_reason": "stop", "message": {"role": "assistant", "content": "done"}
            }]
        },
        _response(1, _call("call-1", "shell", {})),
        _response(1, _call("call-1", "list_files", "not-json")),
    ],
)
def test_chat_runner_rejects_malformed_or_undeclared_provider_output(worktree, bad_response):
    result = OpenAIChatCompletionsAgentRunner(
        ScriptedTransport([bad_response])
    ).run(_case(), worktree)

    assert result["status"] == "FAILED"
    assert result["errorCode"] in {
        "AGENT_CHAT_COMPLETIONS_PROTOCOL_INVALID",
        "AGENT_CUSTOM_TOOL_CALL_INVALID",
    }


def test_chat_runner_enforces_budget_and_submit_deadline(worktree):
    budgets = dict(DEFAULT_AGENT_BUDGETS)
    budgets["submitByTurn"] = 3
    transport = ScriptedTransport([
        _response(1, _call("call-1", "list_files", {})),
        _response(2, _call("call-2", "list_files", {})),
        _response(3, _call("call-3", "list_files", {})),
    ])

    result = OpenAIChatCompletionsAgentRunner(
        transport, ChatCompletionsRunnerConfig.from_budgets(budgets)
    ).run(_case(), worktree)

    assert result["errorCode"] == "AGENT_SUBMIT_DEADLINE_EXCEEDED"
    assert result["toolAudit"]["toolCallCount"] == 2
    assert result["effectiveBudgets"] == budgets


def test_chat_runner_reports_evidence_budget_exhaustion_then_allows_submit(worktree):
    budgets = dict(DEFAULT_AGENT_BUDGETS)
    budgets.update({"maxToolCalls": 10, "maxEvidenceCalls": 4, "convergeAtCalls": 2})
    transport = ScriptedTransport([
        _response(1, *[
            _call(f"call-{index}", "list_files", {}) for index in range(1, 6)
        ]),
        _response(2, _call("call-6", "submit_review", _card())),
    ])

    result = OpenAIChatCompletionsAgentRunner(
        transport, ChatCompletionsRunnerConfig.from_budgets(budgets)
    ).run(_case(), worktree)

    assert result["status"] == "SUCCESS"
    assert result["toolAudit"]["toolCallCount"] == 6
    assert any(
        event.get("errorCode") == "EVIDENCE_COLLECTION_COMPLETE"
        for event in result["toolAudit"]["events"]
    )


def test_chat_runner_stops_after_third_schema_failure_without_next_model_turn(worktree):
    invalid = {"summary": "missing fields"}
    transport = ScriptedTransport(
        [
            _response(turn, _call(f"call-{turn}", "submit_review", invalid))
            for turn in range(1, 5)
        ]
    )

    result = OpenAIChatCompletionsAgentRunner(transport).run(_case(), worktree)

    assert result["status"] == "FAILED"
    assert result["errorCode"] == "AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED"
    assert len(transport.payloads) == 3
    assert result["toolAudit"]["submitAttemptCount"] == 3
    assert result["toolAudit"]["schemaFailureCount"] == 3
    assert result["toolAudit"]["outputTerminationRequested"] is True
    assert result["toolAudit"]["failureChain"][-1]["code"] == (
        "AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED"
    )


def test_chat_runner_cancellation_has_priority_over_schema_exhaustion(worktree):
    cancelled = Event()
    transport = ScriptedTransport(
        [
            _response(
                turn,
                _call(f"call-{turn}", "submit_review", {"summary": "missing"}),
            )
            for turn in range(1, 4)
        ]
    )

    def cancel_when_exhausted(audit):
        if audit.get("outputRepairExhausted"):
            cancelled.set()

    result = OpenAIChatCompletionsAgentRunner(transport).run(
        _case(),
        worktree,
        cancel_event=cancelled,
        progress_callback=cancel_when_exhausted,
    )

    assert result["errorCode"] == "AGENT_CANCELLED"


def test_chat_runner_cancels_before_network(worktree):
    cancelled = Event()
    cancelled.set()
    transport = ScriptedTransport([_response(1, _call("call-1", "submit_review", _card()))])

    result = OpenAIChatCompletionsAgentRunner(transport).run(
        _case(), worktree, cancel_event=cancelled
    )

    assert result["errorCode"] == "AGENT_CANCELLED"
    assert transport.payloads == []


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "AGENT_CUSTOM_AUTH_FAILED"),
        (404, "AGENT_CHAT_COMPLETIONS_UNSUPPORTED"),
        (400, "AGENT_CHAT_COMPLETIONS_PROTOCOL_INVALID"),
        (429, "AGENT_CUSTOM_RATE_LIMITED"),
        (503, "AGENT_CUSTOM_NETWORK_ERROR"),
        (None, "AGENT_CUSTOM_NETWORK_ERROR"),
    ],
)
def test_chat_runner_retries_and_redacts_transport_failures(worktree, status_code, expected):
    result = OpenAIChatCompletionsAgentRunner(
        ScriptedTransport([ChatCompletionsTransportError(status_code=status_code)] * 3),
        ChatCompletionsRunnerConfig(max_retries=2),
        sleeper=lambda _delay: None,
    ).run(_case(), worktree)

    assert result["errorCode"] == expected
    assert "transport failed" not in json.dumps(result)


def test_chat_http_transport_does_not_leak_key_or_error_body(worktree, respx_mock):
    endpoint = "https://relay.example/v1/chat/completions"
    api_key = "SYNTHETIC_CHAT_KEY_MUST_NOT_LEAK"
    raw_error = "relay-secret-chat-error"
    respx_mock.post(endpoint).mock(return_value=httpx.Response(401, text=raw_error))

    result = OpenAIChatCompletionsAgentRunner(
        HttpxChatCompletionsTransport(endpoint, api_key)
    ).run(_case(), worktree)

    serialized = json.dumps(result, ensure_ascii=False)
    assert result["errorCode"] == "AGENT_CUSTOM_AUTH_FAILED"
    assert api_key not in serialized
    assert raw_error not in serialized


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://relay.example/v1/chat/completions",
        "https://relay.example/v1/responses",
        "https://user:secret@relay.example/v1/chat/completions",
        "https://relay.example/v1/chat/completions?debug=true",
    ],
)
def test_chat_http_transport_requires_safe_https_endpoint(endpoint):
    with pytest.raises(ChatCompletionsAgentError) as captured:
        HttpxChatCompletionsTransport(endpoint, "synthetic-key")

    assert captured.value.code == "AGENT_CUSTOM_CONFIG_INCOMPLETE"


def test_chat_synthetic_validation_uses_no_network_and_submits_review():
    assert run_synthetic_validation() == {
        "status": "PASS",
        "runnerStatus": "SUCCESS",
        "errorCode": None,
        "turnCount": 2,
        "toolCallCount": 3,
        "reviewSubmitted": True,
        "retention": {
            "rawResponseSaved": False,
            "reasoningSaved": False,
            "sourceSnippetsSaved": False,
            "toolArgumentsSaved": False,
        },
    }
