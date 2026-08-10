from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
from typing import Any

from app.agent_review_spike.chat_completions_runner import (
    OpenAIChatCompletionsAgentRunner,
)


class SyntheticChatCompletionsTransport:
    """Deterministic protocol fixture; it never opens a network connection."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.turn = 0

    def create(self, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        del timeout_seconds
        self.payloads.append(deepcopy(payload))
        self.turn += 1
        calls = {
            1: [
                _call("call-1", "read_diff_range", {
                    "path": "src/service.py", "startLine": 1, "endLine": 3
                }),
                _call("call-2", "read_file_range", {
                    "path": "src/service.py", "startLine": 1, "endLine": 1
                }),
            ],
            2: [_call("call-3", "submit_review", {
                "summary": "未发现问题", "overallLevel": "LOW", "findings": []
            })],
        }[self.turn]
        return _response(self.turn, calls)


def run_synthetic_validation() -> dict[str, Any]:
    transport = SyntheticChatCompletionsTransport()
    with tempfile.TemporaryDirectory(prefix="chat-completions-synthetic-") as name:
        worktree = Path(name)
        source = worktree / "src" / "service.py"
        source.parent.mkdir(parents=True)
        source.write_text("synthetic source\n", encoding="utf-8")
        result = OpenAIChatCompletionsAgentRunner(transport).run(
            {
                "id": "synthetic-chat-completions-protocol",
                "title": "Synthetic Chat Completions validation",
                "changedFiles": ["src/service.py"],
                "diff": "+++ b/src/service.py\n@@ -1 +1 @@\n-old\n+new",
                "baselineContext": "fixed local fixture",
            },
            worktree,
        )
    return {
        "status": "PASS" if result.get("status") == "SUCCESS" else "FAIL",
        "runnerStatus": result.get("status"),
        "errorCode": result.get("errorCode"),
        "turnCount": result.get("session", {}).get("turnCount"),
        "toolCallCount": result.get("toolAudit", {}).get("toolCallCount"),
        "reviewSubmitted": result.get("toolAudit", {}).get("reviewSubmitted"),
        "retention": result.get("retention"),
    }


def _call(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def _response(turn: int, calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{turn}",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": calls,
                },
            }
        ],
        "usage": {
            "prompt_tokens": turn,
            "completion_tokens": 1,
            "total_tokens": turn + 1,
        },
    }
