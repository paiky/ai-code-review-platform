from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, BinaryIO

from app.agent_review_spike.tool_executor import ReviewToolExecutor, tool_definitions
from app.agent_review_spike.workspace import ReviewWorkspace, ToolBudget


class ReviewMcpServer:
    def __init__(
        self,
        workspace: ReviewWorkspace,
        changed_files: list[str],
        result_path: Path,
        audit_path: Path,
        budget: ToolBudget,
        diff_by_file: dict[str, str] | None = None,
    ) -> None:
        self.executor = ReviewToolExecutor(
            workspace,
            changed_files,
            result_path,
            audit_path,
            budget,
            diff_by_file,
        )
        self.workspace = self.executor.workspace
        self.changed_files = self.executor.changed_files
        self.result_path = self.executor.result_path
        self.audit_path = self.executor.audit_path
        self.budget = self.executor.budget

    def dispatch(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = str(message.get("method") or "")
        request_id = message.get("id")
        if method == "initialize":
            requested = ((message.get("params") or {}).get("protocolVersion")) or "2024-11-05"
            return _response(
                request_id,
                {
                    "protocolVersion": requested,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "readonly-agent-review", "version": "0.1.0"},
                },
            )
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return None
        if method == "ping":
            return _response(request_id, {})
        if method == "tools/list":
            return _response(request_id, {"tools": tool_definitions()})
        if method == "tools/call":
            params = message.get("params") or {}
            return _response(request_id, self.call_tool(params.get("name"), params.get("arguments")))
        return _error(request_id, -32601, "method not found")

    def call_tool(self, name: Any, arguments: Any) -> dict[str, Any]:
        result = self.executor.execute(name, arguments)
        return _tool_content(result.value, is_error=result.is_error)

    @property
    def submitted(self) -> bool:
        return self.executor.submitted

    def _write_audit(self) -> None:
        self.executor.write_audit()


def main() -> int:
    try:
        workspace = ReviewWorkspace(Path(_required_env("REVIEW_WORKTREE_ROOT")))
        changed_files = json.loads(_required_env("REVIEW_CHANGED_FILES_JSON"))
        if not isinstance(changed_files, list):
            raise ValueError("REVIEW_CHANGED_FILES_JSON must be an array")
        server = ReviewMcpServer(
            workspace=workspace,
            changed_files=[str(item) for item in changed_files],
            result_path=Path(_required_env("REVIEW_RESULT_PATH")),
            audit_path=Path(_required_env("REVIEW_AUDIT_PATH")),
            budget=ToolBudget(
                max_calls=int(os.getenv("REVIEW_MAX_TOOL_CALLS", "40")),
                max_source_bytes=int(os.getenv("REVIEW_MAX_SOURCE_BYTES", "200000")),
                max_evidence_calls=int(
                    os.getenv("REVIEW_MAX_EVIDENCE_CALLS", "10")
                ),
                converge_at_evidence_calls=int(
                    os.getenv("REVIEW_CONVERGE_AT_CALLS", "8")
                ),
            ),
            diff_by_file=_load_diff_map(os.getenv("REVIEW_DIFF_MAP_PATH")),
        )
    except Exception as exception:
        print(f"readonly review MCP startup failed: {exception}", file=sys.stderr)
        return 2

    while True:
        message = _read_message(sys.stdin.buffer)
        if message is None:
            break
        try:
            response = server.dispatch(message)
        except Exception:
            response = _error(message.get("id"), -32603, "internal server error")
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    server._write_audit()
    return 0


def _read_message(stream: BinaryIO) -> dict[str, Any] | None:
    first = stream.readline()
    if not first:
        return None
    if first.lower().startswith(b"content-length:"):
        try:
            length = int(first.split(b":", 1)[1].strip())
        except ValueError as exception:
            raise ValueError("invalid Content-Length") from exception
        while True:
            header = stream.readline()
            if not header or header in {b"\n", b"\r\n"}:
                break
        payload = stream.read(length)
    else:
        payload = first.strip()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("MCP message must be an object")
    return value


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _load_diff_map(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    parsed = json.loads(Path(value).read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("REVIEW_DIFF_MAP_PATH must contain an object")
    return {str(key).replace("\\", "/"): str(content) for key, content in parsed.items()}


def _response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_content(value: Any, *, is_error: bool) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            }
        ],
        "isError": is_error,
    }


if __name__ == "__main__":
    raise SystemExit(main())
