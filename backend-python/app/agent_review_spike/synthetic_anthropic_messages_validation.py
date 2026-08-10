from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
from typing import Any

from app.agent_review_spike.anthropic_messages_runner import (
    AnthropicMessagesAgentRunner,
)


class SyntheticAnthropicMessagesTransport:
    """Fixed Messages fixture; it performs no HTTP or SDK calls."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.turn = 0

    def create(self, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        del timeout_seconds
        self.payloads.append(deepcopy(payload))
        self.turn += 1
        blocks = {
            1: [
                _tool_use("tool-1", "read_diff_range", {
                    "path": "src/service.py", "startLine": 1, "endLine": 3
                }),
                _tool_use("tool-2", "read_file_range", {
                    "path": "src/service.py", "startLine": 1, "endLine": 1
                }),
            ],
            2: [_tool_use("tool-3", "submit_review", {
                "summary": "未发现问题", "overallLevel": "LOW", "findings": []
            })],
        }[self.turn]
        return _message(self.turn, blocks)


def run_synthetic_validation() -> dict[str, Any]:
    transport = SyntheticAnthropicMessagesTransport()
    with tempfile.TemporaryDirectory(prefix="anthropic-messages-synthetic-") as name:
        worktree = Path(name)
        source = worktree / "src" / "service.py"
        source.parent.mkdir(parents=True)
        source.write_text("synthetic source\n", encoding="utf-8")
        result = AnthropicMessagesAgentRunner(transport).run(
            {
                "id": "synthetic-anthropic-messages-protocol",
                "title": "Synthetic Anthropic Messages validation",
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


def _tool_use(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": call_id, "name": name, "input": arguments}


def _message(turn: int, content: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": f"msg_{turn}",
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": "synthetic-anthropic-model",
        "stop_reason": "tool_use",
        "usage": {"input_tokens": turn, "output_tokens": 2},
    }
