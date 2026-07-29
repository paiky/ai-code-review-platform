from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, BinaryIO

from app.agent_review_spike.schema import (
    ReviewSchemaError,
    review_card_input_schema,
    validate_review_card,
)
from app.agent_review_spike.workspace import (
    EVIDENCE_TOOLS,
    ReviewToolError,
    ReviewWorkspace,
    ToolBudget,
)


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_files",
            "description": "List safe source files inside the current review worktree.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pattern": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                },
            },
        },
        {
            "name": "search_code",
            "description": "Search safe text source files inside the current review worktree.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "globs": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                    "isRegex": {"type": "boolean"},
                    "caseSensitive": {"type": "boolean"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        },
        {
            "name": "read_file_range",
            "description": "Read at most 400 lines from one safe source file.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "startLine", "endLine"],
                "properties": {
                    "path": {"type": "string"},
                    "startLine": {"type": "integer", "minimum": 1},
                    "endLine": {"type": "integer", "minimum": 1},
                },
            },
        },
        {
            "name": "read_diff_range",
            "description": "Read at most 400 lines of the task diff for one changed file.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "startLine", "endLine"],
                "properties": {
                    "path": {"type": "string"},
                    "startLine": {"type": "integer", "minimum": 1},
                    "endLine": {"type": "integer", "minimum": 1},
                },
            },
        },
        {
            "name": "submit_review",
            "description": "Validate and submit the final platform Review Card exactly once.",
            "inputSchema": review_card_input_schema(),
        },
    ]


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
        self.workspace = workspace
        self.changed_files = changed_files
        self.result_path = result_path
        self.audit_path = audit_path
        self.budget = budget
        self.diff_by_file = diff_by_file or {}
        self.submitted = False

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
        tool = str(name or "")
        args = arguments if isinstance(arguments, dict) else {}
        started = None
        try:
            started = self.budget.begin(tool)
            if tool == "list_files":
                value = self.workspace.list_files(args.get("pattern") or "**/*", args.get("limit") or 200)
                paths = [item["path"] for item in value["files"]]
                self.budget.finish(tool, started, item_count=value["count"], paths=paths)
            elif tool == "search_code":
                value = self.workspace.search_code(
                    args.get("query"),
                    globs=args.get("globs"),
                    is_regex=bool(args.get("isRegex", False)),
                    case_sensitive=bool(args.get("caseSensitive", True)),
                    limit=args.get("limit") or 50,
                )
                paths = [item["path"] for item in value["matches"]]
                source_bytes = sum(
                    len(item["text"].encode("utf-8")) for item in value["matches"]
                )
                self.budget.finish(
                    tool,
                    started,
                    source_bytes=source_bytes,
                    item_count=value["count"],
                    paths=paths,
                    query=str(args.get("query") or ""),
                )
            elif tool == "read_file_range":
                value = self.workspace.read_file_range(
                    args.get("path"), args.get("startLine"), args.get("endLine")
                )
                self.budget.finish(
                    tool,
                    started,
                    source_bytes=len(value["content"].encode("utf-8")),
                    item_count=value["lineCount"],
                    paths=[value["path"]],
                )
            elif tool == "read_diff_range":
                path = str(args.get("path") or "").replace("\\", "/")
                if path not in self.changed_files or path not in self.diff_by_file:
                    raise ReviewToolError("DIFF_PATH_NOT_ALLOWED", "diff path is not a changed file")
                start_line = int(args.get("startLine") or 0)
                end_line = int(args.get("endLine") or 0)
                if start_line < 1 or end_line < start_line or end_line - start_line + 1 > 400:
                    raise ReviewToolError("INVALID_ARGUMENT", "diff range must contain 1 to 400 lines")
                lines = self.diff_by_file[path].splitlines()
                content = "\n".join(lines[start_line - 1 : end_line])
                value = {"path": path, "startLine": start_line, "endLine": min(end_line, len(lines)), "lineCount": len(lines[start_line - 1 : end_line]), "content": content}
                self.budget.finish(tool, started, source_bytes=len(content.encode("utf-8")), item_count=value["lineCount"], paths=[path])
            elif tool == "submit_review":
                if self.submitted:
                    raise ReviewToolError("REVIEW_ALREADY_SUBMITTED", "submit_review may only be called once")
                card = validate_review_card(args, self.changed_files)
                _atomic_write_json(self.result_path, card)
                self.submitted = True
                value = {"accepted": True, "findingCount": len(card["findings"])}
                self.budget.finish(tool, started, item_count=len(card["findings"]))
            else:
                raise ReviewToolError("TOOL_NOT_ALLOWED", "tool is not available")
            self._write_audit()
            return _tool_content(self._with_review_budget(tool, value), is_error=False)
        except (ReviewToolError, ReviewSchemaError) as exception:
            if isinstance(exception, ReviewToolError):
                error_code = exception.code
            else:
                error_code = "REVIEW_SCHEMA_INVALID"
            if error_code in {
                "PATH_OUTSIDE_WORKTREE",
                "SENSITIVE_PATH_DENIED",
                "SYMLINK_DENIED",
            }:
                self.budget.blocked()
            if started is not None:
                try:
                    self.budget.finish(
                        tool,
                        started,
                        status="FAILED",
                        error_code=error_code,
                        query=str(args.get("query")) if tool == "search_code" else None,
                    )
                except ReviewToolError:
                    pass
            self._write_audit()
            return _tool_content(
                self._with_review_budget(
                    tool,
                    {"errorCode": error_code, "message": str(exception)},
                ),
                is_error=True,
            )
        except Exception:
            if started is not None:
                try:
                    self.budget.finish(
                        tool,
                        started,
                        status="FAILED",
                        error_code="INTERNAL_TOOL_ERROR",
                    )
                except ReviewToolError:
                    pass
            self._write_audit()
            return _tool_content(
                self._with_review_budget(
                    tool,
                    {
                        "errorCode": "INTERNAL_TOOL_ERROR",
                        "message": "tool execution failed",
                    },
                ),
                is_error=True,
            )

    def _with_review_budget(self, tool: str, value: dict[str, Any]) -> dict[str, Any]:
        if tool not in EVIDENCE_TOOLS:
            return value
        return {**value, "reviewBudget": self.budget.review_budget()}

    def _write_audit(self) -> None:
        summary = self.budget.summary()
        summary["reviewSubmitted"] = self.submitted
        _atomic_write_json(self.audit_path, summary)


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


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=f".{path.name}."
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        temporary = Path(handle.name)
    os.replace(temporary, path)


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
