from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any

from app.agent_review_spike.responses_runner import (
    OpenAIResponsesAgentRunner,
    ResponsesRunnerConfig,
)


SYNTHETIC_SOURCE = """def divide(total: int, count: int) -> float:
    return total / count
"""


class SyntheticResponsesTransport:
    """Deterministic in-process Responses service; it never performs network I/O."""

    def __init__(self) -> None:
        self.turn = 0

    def create(self, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        self.turn += 1
        call = {
            1: ("read_diff_range", {"path": "src/service.py", "startLine": 1, "endLine": 3}),
            2: ("read_file_range", {"path": "src/service.py", "startLine": 1, "endLine": 2}),
            3: (
                "submit_review",
                {"summary": "synthetic 验证完成", "overallLevel": "LOW", "findings": []},
            ),
        }.get(self.turn)
        if call is None:
            return _response(self.turn, [])
        name, arguments = call
        output = [
            {
                "type": "reasoning",
                "id": f"rs_{self.turn}",
                "encrypted_content": f"synthetic-{self.turn}",
                "summary": [],
            },
            {
                "type": "function_call",
                "id": f"fc_{self.turn}",
                "call_id": f"call_{self.turn}",
                "name": name,
                "arguments": json.dumps(arguments, ensure_ascii=False),
            },
        ]
        return _response(self.turn, output)


def run_synthetic_validation() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="responses-synthetic-") as temporary_name:
        worktree = Path(temporary_name)
        source = worktree / "src" / "service.py"
        source.parent.mkdir(parents=True)
        source.write_text(SYNTHETIC_SOURCE, encoding="utf-8")
        case = {
            "id": "synthetic-responses-protocol",
            "title": "Synthetic Responses protocol validation",
            "changedFiles": ["src/service.py"],
            "diff": "+++ b/src/service.py\n@@ -0,0 +1,2 @@\n+def divide(total, count):\n+    return total / count",
            "baselineContext": "synthetic-only",
        }
        result = OpenAIResponsesAgentRunner(
            SyntheticResponsesTransport(),
            ResponsesRunnerConfig(),
        ).run(case, worktree)
    return {
        "status": "PASS" if result["status"] == "SUCCESS" else "FAIL",
        "runnerStatus": result["status"],
        "errorCode": result.get("errorCode"),
        "turnCount": result["session"]["turnCount"],
        "toolCallCount": result["toolAudit"].get("toolCallCount", 0),
        "reviewSubmitted": result["toolAudit"].get("reviewSubmitted", False),
        "retention": result["retention"],
    }


def main() -> int:
    result = run_synthetic_validation()
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1


def _response(turn: int, output: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": f"resp_{turn}",
        "object": "response",
        "status": "completed",
        "output": output,
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }


if __name__ == "__main__":
    raise SystemExit(main())
