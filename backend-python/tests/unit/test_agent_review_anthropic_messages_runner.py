from __future__ import annotations

from copy import deepcopy
import json
from threading import Event
from typing import Any

import httpx
import pytest

from app.agent_review_spike.anthropic_messages_runner import (
    AnthropicMessagesAgentError,
    AnthropicMessagesAgentRunner,
    AnthropicMessagesRunnerConfig,
    AnthropicMessagesTransportError,
    HttpxAnthropicMessagesTransport,
)
from app.agent_review_spike.budgets import DEFAULT_AGENT_BUDGETS
from app.agent_review_spike.synthetic_anthropic_messages_validation import (
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
    source.write_text("UNIQUE_ANTHROPIC_SOURCE_SECRET\nsecond line\n", encoding="utf-8")
    return tmp_path


def _case() -> dict[str, Any]:
    return {
        "id": "anthropic-unit",
        "title": "Anthropic Messages unit test",
        "changedFiles": ["src/service.py"],
        "diff": "+++ b/src/service.py\n@@ -1 +1 @@\n-old\n+UNIQUE_ANTHROPIC_DIFF_SECRET",
        "baselineContext": "bounded synthetic context",
    }


def _card() -> dict[str, Any]:
    return {"summary": "未发现问题", "overallLevel": "LOW", "findings": []}


def _tool_use(call_id: str, name: str, arguments: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": call_id, "name": name, "input": arguments}


def _message(turn: int, *blocks: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"msg_{turn}",
        "type": "message",
        "role": "assistant",
        "content": list(blocks),
        "model": "synthetic-anthropic-model",
        "stop_reason": "tool_use",
        "usage": {
            "input_tokens": turn,
            "output_tokens": 2,
            "unsafe_detail": "must-not-be-retained",
        },
    }


def test_messages_runner_continues_tool_results_and_submits_review(worktree):
    transport = ScriptedTransport([
        _message(
            1,
            _tool_use("tool-1", "read_diff_range", {
                "path": "src/service.py", "startLine": 1, "endLine": 3
            }),
            _tool_use("tool-2", "read_file_range", {
                "path": "src/service.py", "startLine": 1, "endLine": 2
            }),
        ),
        _message(2, _tool_use("tool-3", "submit_review", _card())),
    ])

    result = AnthropicMessagesAgentRunner(transport).run(_case(), worktree)

    assert result["status"] == "SUCCESS"
    assert result["card"] == _card()
    assert result["session"] == {
        "turnCount": 2,
        "usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
    }
    assert result["toolAudit"]["toolCallCount"] == 3
    first = transport.payloads[0]
    assert first["tool_choice"] == {"type": "any"}
    assert first["max_tokens"] == 4096
    assert {item["name"] for item in first["tools"]} == {
        "list_files", "search_code", "read_file_range", "read_diff_range", "submit_review"
    }
    continued = transport.payloads[1]["messages"]
    assert continued[-2]["role"] == "assistant"
    assert continued[-1]["role"] == "user"
    assert [item["tool_use_id"] for item in continued[-1]["content"]] == [
        "tool-1", "tool-2"
    ]
    assert all(item["type"] == "tool_result" for item in continued[-1]["content"])
    serialized = json.dumps(result, ensure_ascii=False)
    assert "UNIQUE_ANTHROPIC_SOURCE_SECRET" not in serialized
    assert "UNIQUE_ANTHROPIC_DIFF_SECRET" not in serialized
    assert "src/service.py" not in serialized
    assert "unsafe_detail" not in serialized


@pytest.mark.parametrize(
    "bad_response",
    [
        {"id": "msg_bad", "type": "message", "role": "assistant", "content": []},
        {
            "id": "msg_bad", "type": "message", "role": "assistant",
            "stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}],
        },
        _message(1, {"type": "server_tool_use", "id": "tool-1"}),
        _message(1, _tool_use("tool-1", "shell", {})),
        _message(1, _tool_use("tool-1", "list_files", "not-an-object")),
    ],
)
def test_messages_runner_rejects_damaged_or_undeclared_output(worktree, bad_response):
    result = AnthropicMessagesAgentRunner(
        ScriptedTransport([bad_response])
    ).run(_case(), worktree)

    assert result["status"] == "FAILED"
    assert result["errorCode"] in {
        "AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID",
        "AGENT_CUSTOM_TOOL_CALL_INVALID",
    }


def test_messages_runner_reports_budget_exhaustion_then_allows_submit(worktree):
    budgets = dict(DEFAULT_AGENT_BUDGETS)
    budgets.update({"maxToolCalls": 10, "maxEvidenceCalls": 4, "convergeAtCalls": 2})
    transport = ScriptedTransport([
        _message(1, *[
            _tool_use(f"tool-{index}", "list_files", {}) for index in range(1, 6)
        ]),
        _message(2, _tool_use("tool-6", "submit_review", _card())),
    ])

    result = AnthropicMessagesAgentRunner(
        transport, AnthropicMessagesRunnerConfig.from_budgets(budgets)
    ).run(_case(), worktree)

    assert result["status"] == "SUCCESS"
    assert any(
        event.get("errorCode") == "EVIDENCE_COLLECTION_COMPLETE"
        for event in result["toolAudit"]["events"]
    )
    tool_results = transport.payloads[1]["messages"][-1]["content"]
    assert tool_results[-1]["is_error"] is True


def test_messages_runner_cancels_before_network(worktree):
    cancelled = Event()
    cancelled.set()
    transport = ScriptedTransport([_message(1, _tool_use("tool-1", "submit_review", _card()))])

    result = AnthropicMessagesAgentRunner(transport).run(
        _case(), worktree, cancel_event=cancelled
    )

    assert result["errorCode"] == "AGENT_CANCELLED"
    assert transport.payloads == []


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "AGENT_CUSTOM_AUTH_FAILED"),
        (404, "AGENT_ANTHROPIC_MESSAGES_UNSUPPORTED"),
        (400, "AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID"),
        (429, "AGENT_CUSTOM_RATE_LIMITED"),
        (503, "AGENT_CUSTOM_NETWORK_ERROR"),
        (None, "AGENT_CUSTOM_NETWORK_ERROR"),
    ],
)
def test_messages_runner_retries_and_redacts_transport_failures(
    worktree, status_code, expected
):
    result = AnthropicMessagesAgentRunner(
        ScriptedTransport([AnthropicMessagesTransportError(status_code=status_code)] * 3),
        AnthropicMessagesRunnerConfig(max_retries=2),
        sleeper=lambda _delay: None,
    ).run(_case(), worktree)

    assert result["errorCode"] == expected
    assert "transport failed" not in json.dumps(result)


def test_messages_http_transport_uses_anthropic_headers_without_leaks(
    worktree, respx_mock
):
    endpoint = "https://relay.example/v1/messages"
    api_key = "SYNTHETIC_ANTHROPIC_KEY_MUST_NOT_LEAK"
    raw_error = "relay-secret-anthropic-error"
    route = respx_mock.post(endpoint).mock(return_value=httpx.Response(401, text=raw_error))

    result = AnthropicMessagesAgentRunner(
        HttpxAnthropicMessagesTransport(endpoint, api_key)
    ).run(_case(), worktree)

    request = route.calls[0].request
    assert request.headers["x-api-key"] == api_key
    assert request.headers["anthropic-version"] == "2023-06-01"
    serialized = json.dumps(result, ensure_ascii=False)
    assert result["errorCode"] == "AGENT_CUSTOM_AUTH_FAILED"
    assert api_key not in serialized
    assert raw_error not in serialized


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://relay.example/v1/messages",
        "https://relay.example/v1/responses",
        "https://user:secret@relay.example/v1/messages",
        "https://relay.example/v1/messages?debug=true",
    ],
)
def test_messages_http_transport_requires_safe_https_endpoint(endpoint):
    with pytest.raises(AnthropicMessagesAgentError) as captured:
        HttpxAnthropicMessagesTransport(endpoint, "synthetic-key")

    assert captured.value.code == "AGENT_CUSTOM_CONFIG_INCOMPLETE"


def test_anthropic_synthetic_validation_uses_no_network_and_submits_review():
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
