from __future__ import annotations

from copy import deepcopy
import json
from threading import Event
from typing import Any

import httpx
import pytest

from app.agent_review_spike.budgets import DEFAULT_AGENT_BUDGETS
from app.agent_review_spike.responses_runner import (
    OpenAIResponsesAgentRunner,
    HttpxResponsesTransport,
    ResponsesAgentError,
    ResponsesRunnerConfig,
    ResponsesTransportError,
)
from app.agent_review_spike.synthetic_responses_validation import run_synthetic_validation


class ScriptedTransport:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.payloads: list[dict[str, Any]] = []
        self.timeouts: list[float] = []

    def create(self, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        self.payloads.append(deepcopy(payload))
        self.timeouts.append(timeout_seconds)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _case(diff: str | None = None) -> dict[str, Any]:
    return {
        "id": "responses-unit",
        "title": "Responses unit test",
        "changedFiles": ["src/service.py"],
        "diff": diff
        or "+++ b/src/service.py\n@@ -1 +1 @@\n-old = 1\n+new = UNIQUE_SOURCE_SECRET",
        "baselineContext": "bounded synthetic context",
    }


@pytest.fixture
def worktree(tmp_path):
    source = tmp_path / "src" / "service.py"
    source.parent.mkdir(parents=True)
    source.write_text("UNIQUE_SOURCE_SECRET\nsecond line\n", encoding="utf-8")
    return tmp_path


def _response(turn: int, *items: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"resp_{turn}",
        "object": "response",
        "status": "completed",
        "output": list(items),
        "usage": {
            "input_tokens": turn,
            "output_tokens": 2,
            "total_tokens": turn + 2,
            "unsafe_detail": "must-not-be-retained",
        },
    }


def _reasoning(turn: int) -> dict[str, Any]:
    return {
        "type": "reasoning",
        "id": f"rs_{turn}",
        "encrypted_content": f"encrypted-{turn}",
        "summary": [],
    }


def _call(turn: int, name: str, arguments: Any) -> dict[str, Any]:
    encoded = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {
        "type": "function_call",
        "id": f"fc_{turn}",
        "call_id": f"call_{turn}",
        "name": name,
        "arguments": encoded,
    }


def _card() -> dict[str, Any]:
    return {"summary": "未发现问题", "overallLevel": "LOW", "findings": []}


def test_responses_runner_replays_reasoning_and_completes_three_tool_rounds(worktree):
    transport = ScriptedTransport(
        [
            _response(1, _reasoning(1), _call(1, "read_diff_range", {
                "path": "src/service.py", "startLine": 1, "endLine": 3
            })),
            _response(2, _reasoning(2), _call(2, "read_file_range", {
                "path": "src/service.py", "startLine": 1, "endLine": 2
            })),
            _response(3, _reasoning(3), _call(3, "submit_review", _card())),
        ]
    )

    result = OpenAIResponsesAgentRunner(transport).run(_case(), worktree)

    assert result["status"] == "SUCCESS"
    assert result["session"] == {
        "turnCount": 3,
        "usage": {"input_tokens": 6, "output_tokens": 6, "total_tokens": 12},
    }
    assert result["toolAudit"]["toolCallCount"] == 3
    assert result["toolAudit"]["reviewSubmitted"] is True
    first = transport.payloads[0]
    assert first["model"] == "gpt-5.6-sol"
    assert first["reasoning"] == {"effort": "high"}
    assert first["parallel_tool_calls"] is False
    assert first["store"] is False
    assert first["include"] == ["reasoning.encrypted_content"]
    assert {item["name"] for item in first["tools"]} == {
        "list_files", "search_code", "read_file_range", "read_diff_range", "submit_review"
    }
    second_input = transport.payloads[1]["input"]
    assert _reasoning(1) in second_input
    assert any(
        item.get("type") == "function_call_output" and item.get("call_id") == "call_1"
        for item in second_input
    )
    safe_text = json.dumps(result, ensure_ascii=False)
    assert "UNIQUE_SOURCE_SECRET" not in safe_text
    assert "src/service.py" not in safe_text
    assert "encrypted-" not in safe_text
    assert "unsafe_detail" not in safe_text


def test_responses_runner_stops_after_third_schema_failure_without_next_model_turn(
    worktree,
):
    invalid = {"summary": "missing fields"}
    transport = ScriptedTransport(
        [
            _response(
                turn,
                _reasoning(turn),
                _call(turn, "submit_review", invalid),
            )
            for turn in range(1, 5)
        ]
    )

    result = OpenAIResponsesAgentRunner(transport).run(_case(), worktree)

    assert result["status"] == "FAILED"
    assert result["errorCode"] == "AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED"
    assert len(transport.payloads) == 3
    assert result["toolAudit"]["submitAttemptCount"] == 3
    assert result["toolAudit"]["schemaFailureCount"] == 3
    assert result["toolAudit"]["outputRepairExhausted"] is True


def test_responses_runner_pages_diff_above_inline_budget(worktree):
    budgets = dict(DEFAULT_AGENT_BUDGETS)
    budgets["inlineDiffBytes"] = 10_000
    transport = ScriptedTransport([_response(1, _call(1, "submit_review", _card()))])
    large_diff = "+++ b/src/service.py\n" + ("+secret-source-line\n" * 700)

    result = OpenAIResponsesAgentRunner(
        transport, ResponsesRunnerConfig.from_budgets(budgets)
    ).run(_case(large_diff), worktree)

    assert result["status"] == "SUCCESS"
    prompt = transport.payloads[0]["input"][0]["content"][0]["text"]
    assert "Use read_diff_range" in prompt
    assert "secret-source-line" not in prompt
    assert result["effectiveBudgets"] == budgets


@pytest.mark.parametrize(
    ("bad_item", "error_code"),
    [
        ({"type": "web_search_call", "id": "web_1"}, "AGENT_CUSTOM_TOOL_CALL_INVALID"),
        (_call(1, "shell", {}), "AGENT_CUSTOM_TOOL_CALL_INVALID"),
        (_call(1, "list_files", "not-json"), "AGENT_CUSTOM_TOOL_CALL_INVALID"),
    ],
)
def test_responses_runner_rejects_undeclared_items_and_invalid_calls(
    worktree, bad_item, error_code
):
    result = OpenAIResponsesAgentRunner(
        ScriptedTransport([_response(1, bad_item)])
    ).run(_case(), worktree)

    assert result["status"] == "FAILED"
    assert result["errorCode"] == error_code
    assert set(result) >= {"message", "retention", "effectiveBudgets"}


def test_responses_runner_rejects_duplicate_call_id(worktree):
    second = _call(2, "submit_review", _card())
    second["call_id"] = "call_1"
    transport = ScriptedTransport(
        [
            _response(1, _call(1, "list_files", {})),
            _response(2, second),
        ]
    )

    result = OpenAIResponsesAgentRunner(transport).run(_case(), worktree)

    assert result["errorCode"] == "AGENT_CUSTOM_TOOL_CALL_INVALID"
    assert result["toolAudit"]["toolCallCount"] == 1


def test_responses_runner_enforces_submit_turn_without_losing_audit(worktree):
    budgets = dict(DEFAULT_AGENT_BUDGETS)
    budgets["submitByTurn"] = 3
    transport = ScriptedTransport(
        [
            _response(1, _call(1, "list_files", {})),
            _response(2, _call(2, "list_files", {})),
            _response(3, _call(3, "list_files", {})),
        ]
    )

    result = OpenAIResponsesAgentRunner(
        transport, ResponsesRunnerConfig.from_budgets(budgets)
    ).run(_case(), worktree)

    assert result["errorCode"] == "AGENT_SUBMIT_DEADLINE_EXCEEDED"
    assert result["toolAudit"]["toolCallCount"] == 2


def test_responses_runner_enforces_cancellation_before_network(worktree):
    transport = ScriptedTransport([_response(1, _call(1, "submit_review", _card()))])
    cancelled = Event()
    cancelled.set()

    result = OpenAIResponsesAgentRunner(transport).run(
        _case(), worktree, cancel_event=cancelled
    )

    assert result["errorCode"] == "AGENT_CANCELLED"
    assert transport.payloads == []


def test_responses_runner_enforces_overall_deadline_before_network(worktree):
    ticks = iter([0.0, 600.0])
    transport = ScriptedTransport([_response(1, _call(1, "submit_review", _card()))])
    runner = OpenAIResponsesAgentRunner(transport, clock=lambda: next(ticks))

    result = runner.run(_case(), worktree)

    assert result["errorCode"] == "AGENT_TIMEOUT"
    assert transport.payloads == []


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "AGENT_CUSTOM_AUTH_FAILED"),
        (404, "AGENT_RESPONSES_UNSUPPORTED"),
        (400, "AGENT_RESPONSES_PROTOCOL_INVALID"),
        (429, "AGENT_CUSTOM_RATE_LIMITED"),
        (503, "AGENT_CUSTOM_NETWORK_ERROR"),
        (None, "AGENT_CUSTOM_NETWORK_ERROR"),
    ],
)
def test_responses_runner_maps_transport_failures_without_raw_body(
    worktree, status_code, expected
):
    failures = [ResponsesTransportError(status_code=status_code)] * 3
    result = OpenAIResponsesAgentRunner(
        ScriptedTransport(failures),
        ResponsesRunnerConfig(max_retries=2),
        sleeper=lambda _delay: None,
    ).run(_case(), worktree)

    assert result["errorCode"] == expected
    assert "Responses transport failed" not in json.dumps(result)


def test_http_transport_does_not_leak_key_or_relay_error_body(worktree, respx_mock):
    endpoint = "https://relay.example/v1/responses"
    api_key = "SYNTHETIC_API_KEY_MUST_NOT_LEAK"
    raw_error = "relay-secret-raw-error-body"
    respx_mock.post(endpoint).mock(return_value=httpx.Response(401, text=raw_error))

    result = OpenAIResponsesAgentRunner(
        HttpxResponsesTransport(endpoint, api_key)
    ).run(_case(), worktree)

    safe_text = json.dumps(result, ensure_ascii=False)
    assert result["errorCode"] == "AGENT_CUSTOM_AUTH_FAILED"
    assert api_key not in safe_text
    assert raw_error not in safe_text


def test_http_transport_forwards_explicit_tls_verification_setting(monkeypatch):
    captured = {}

    def fake_post(_url, **kwargs):
        captured.update(kwargs)
        return httpx.Response(200, json={"id": "response-1", "output": []})

    monkeypatch.setattr(httpx, "post", fake_post)

    HttpxResponsesTransport(
        "https://relay.example/v1/responses",
        "synthetic-key",
        verify_tls=False,
    ).create({"model": "synthetic"}, 1)

    assert captured["verify"] is False


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://relay.example/v1/responses",
        "https://relay.example/v1/chat/completions",
        "https://user:secret@relay.example/v1/responses",
        "https://relay.example/v1/responses?debug=true",
    ],
)
def test_http_transport_requires_safe_https_responses_endpoint(endpoint):
    with pytest.raises(ResponsesAgentError) as captured:
        HttpxResponsesTransport(endpoint, "synthetic-key")

    assert captured.value.code == "AGENT_CUSTOM_CONFIG_INCOMPLETE"


def test_responses_runner_tool_budget_and_review_schema_are_shared(worktree):
    transport = ScriptedTransport(
        [
            _response(1, _call(1, "read_file_range", {
                "path": "src/service.py", "startLine": 1, "endLine": 2
            })),
            _response(2, _call(2, "submit_review", {"summary": "missing schema"})),
            _response(3, _call(3, "submit_review", _card())),
        ]
    )

    result = OpenAIResponsesAgentRunner(transport).run(_case(), worktree)

    assert result["status"] == "SUCCESS"
    assert [item["errorCode"] for item in result["toolAudit"]["events"] if "errorCode" in item] == [
        "REVIEW_SCHEMA_INVALID"
    ]
    assert result["toolAudit"]["sourceBytesReturned"] > 0


def test_synthetic_protocol_validation_uses_no_network_and_submits_review():
    result = run_synthetic_validation()

    assert result == {
        "status": "PASS",
        "runnerStatus": "SUCCESS",
        "errorCode": None,
        "turnCount": 3,
        "toolCallCount": 3,
        "reviewSubmitted": True,
        "retention": {
            "rawResponseSaved": False,
            "reasoningSaved": False,
            "sourceSnippetsSaved": False,
            "toolArgumentsSaved": False,
        },
    }
