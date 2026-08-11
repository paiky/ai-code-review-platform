from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any

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


_MAX_REVIEW_SCHEMA_SUBMIT_ATTEMPTS = 3


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


@dataclass(frozen=True)
class ToolExecutionResult:
    value: dict[str, Any]
    is_error: bool


class ReviewToolExecutor:
    """Shared safety boundary for MCP and Responses function tools."""

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
        self.submit_attempt_count = 0
        self.schema_failure_count = 0
        self.last_schema_failures: list[dict[str, str]] = []
        self.output_repair_exhausted = False
        self.output_termination_requested = False

    def execute(self, name: Any, arguments: Any) -> ToolExecutionResult:
        tool = str(name or "")
        args = arguments if isinstance(arguments, dict) else {}
        if self.output_repair_exhausted:
            return ToolExecutionResult(
                {
                    "errorCode": "AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED",
                    "message": "Review Card schema repair attempts are exhausted",
                    "attempt": self.submit_attempt_count,
                    "maxAttempts": _MAX_REVIEW_SCHEMA_SUBMIT_ATTEMPTS,
                    "retryable": False,
                    "mustSubmit": False,
                },
                True,
            )
        started = None
        try:
            started = self.budget.begin(tool)
            value = self._execute_allowed_tool(tool, args, started)
            self.write_audit()
            return ToolExecutionResult(self._with_review_budget(tool, value), False)
        except (ReviewToolError, ReviewSchemaError) as exception:
            error_code = (
                exception.code
                if isinstance(exception, ReviewToolError)
                else "REVIEW_SCHEMA_INVALID"
            )
            error_value: dict[str, Any] = {
                "errorCode": error_code,
                "message": str(exception),
            }
            if isinstance(exception, ReviewSchemaError) and tool == "submit_review":
                self.schema_failure_count += 1
                self.last_schema_failures = list(exception.violations)
                exhausted = (
                    self.submit_attempt_count
                    >= _MAX_REVIEW_SCHEMA_SUBMIT_ATTEMPTS
                )
                if exhausted:
                    self.output_repair_exhausted = True
                    self.output_termination_requested = True
                error_value = {
                    **exception.safe_contract(),
                    "message": str(exception),
                    "attempt": self.submit_attempt_count,
                    "maxAttempts": _MAX_REVIEW_SCHEMA_SUBMIT_ATTEMPTS,
                    "retryable": not exhausted,
                    "mustSubmit": not exhausted,
                }
            if error_code in {
                "PATH_OUTSIDE_WORKTREE",
                "SENSITIVE_PATH_DENIED",
                "SYMLINK_DENIED",
            }:
                self.budget.blocked()
            self._finish_failed(tool, args, started, error_code)
            if isinstance(exception, ReviewSchemaError) and tool == "submit_review":
                self._annotate_submit_event(exception)
            self.write_audit()
            return ToolExecutionResult(
                self._with_review_budget(
                    tool,
                    error_value,
                ),
                True,
            )
        except Exception:
            self._finish_failed(tool, args, started, "INTERNAL_TOOL_ERROR")
            self.write_audit()
            return ToolExecutionResult(
                self._with_review_budget(
                    tool,
                    {
                        "errorCode": "INTERNAL_TOOL_ERROR",
                        "message": "tool execution failed",
                    },
                ),
                True,
            )

    def write_audit(self) -> None:
        _atomic_write_json(self.audit_path, self.audit_summary())

    def audit_summary(self) -> dict[str, Any]:
        failure_chain: list[dict[str, Any]] = []
        if self.schema_failure_count:
            failure_chain.append(
                {"code": "REVIEW_SCHEMA_INVALID", "count": self.schema_failure_count}
            )
        if self.output_repair_exhausted:
            failure_chain.append(
                {"code": "AGENT_REVIEW_SCHEMA_RETRY_EXHAUSTED", "count": 1}
            )
        return self.budget.summary() | {
            "reviewSubmitted": self.submitted,
            "submitAttemptCount": self.submit_attempt_count,
            "schemaFailureCount": self.schema_failure_count,
            "lastSchemaFailures": list(self.last_schema_failures),
            "outputRepairExhausted": self.output_repair_exhausted,
            "outputTerminationRequested": self.output_termination_requested,
            "failureChain": failure_chain,
        }

    def _execute_allowed_tool(
        self, tool: str, args: dict[str, Any], started: float
    ) -> dict[str, Any]:
        if tool == "list_files":
            value = self.workspace.list_files(args.get("pattern") or "**/*", args.get("limit") or 200)
            paths = [item["path"] for item in value["files"]]
            self.budget.finish(tool, started, item_count=value["count"], paths=paths)
            return value
        if tool == "search_code":
            value = self.workspace.search_code(
                args.get("query"),
                globs=args.get("globs"),
                is_regex=bool(args.get("isRegex", False)),
                case_sensitive=bool(args.get("caseSensitive", True)),
                limit=args.get("limit") or 50,
            )
            paths = [item["path"] for item in value["matches"]]
            source_bytes = sum(len(item["text"].encode("utf-8")) for item in value["matches"])
            self.budget.finish(
                tool,
                started,
                source_bytes=source_bytes,
                item_count=value["count"],
                paths=paths,
                query=str(args.get("query") or ""),
            )
            return value
        if tool == "read_file_range":
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
            return value
        if tool == "read_diff_range":
            path = str(args.get("path") or "").replace("\\", "/")
            if path not in self.changed_files or path not in self.diff_by_file:
                raise ReviewToolError("DIFF_PATH_NOT_ALLOWED", "diff path is not a changed file")
            start_line = int(args.get("startLine") or 0)
            end_line = int(args.get("endLine") or 0)
            if start_line < 1 or end_line < start_line or end_line - start_line + 1 > 400:
                raise ReviewToolError("INVALID_ARGUMENT", "diff range must contain 1 to 400 lines")
            lines = self.diff_by_file[path].splitlines()
            selected = lines[start_line - 1 : end_line]
            content = "\n".join(selected)
            value = {
                "path": path,
                "startLine": start_line,
                "endLine": min(end_line, len(lines)),
                "lineCount": len(selected),
                "content": content,
            }
            self.budget.finish(
                tool,
                started,
                source_bytes=len(content.encode("utf-8")),
                item_count=value["lineCount"],
                paths=[path],
            )
            return value
        if tool == "submit_review":
            if self.submitted:
                raise ReviewToolError(
                    "REVIEW_ALREADY_SUBMITTED", "submit_review may only be called once"
                )
            self.submit_attempt_count += 1
            card = validate_review_card(args, self.changed_files)
            _atomic_write_json(self.result_path, card)
            self.submitted = True
            self.budget.finish(tool, started, item_count=len(card["findings"]))
            self._annotate_submit_event()
            return {"accepted": True, "findingCount": len(card["findings"])}
        raise ReviewToolError("TOOL_NOT_ALLOWED", "tool is not available")

    def _finish_failed(
        self,
        tool: str,
        args: dict[str, Any],
        started: float | None,
        error_code: str,
    ) -> None:
        if started is None:
            return
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

    def _annotate_submit_event(
        self, exception: ReviewSchemaError | None = None
    ) -> None:
        if not self.budget.events or self.budget.events[-1].get("tool") != "submit_review":
            return
        event = self.budget.events[-1]
        event["attempt"] = self.submit_attempt_count
        event["maxAttempts"] = _MAX_REVIEW_SCHEMA_SUBMIT_ATTEMPTS
        if exception is not None:
            event["violations"] = list(exception.violations)
            event["violationCount"] = exception.violation_count
            event["violationsTruncated"] = exception.violations_truncated

    def _with_review_budget(self, tool: str, value: dict[str, Any]) -> dict[str, Any]:
        if tool not in EVIDENCE_TOOLS:
            return value
        return {**value, "reviewBudget": self.budget.review_budget()}


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=f".{path.name}."
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        temporary = Path(handle.name)
    os.replace(temporary, path)
