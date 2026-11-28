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


def tool_definitions(*, context_review: bool = False) -> list[dict[str, Any]]:
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
            "description": (
                "Read up to 500 lines from one safe source file. Long lines and large results are truncated. "
                "Use the returned endLine to continue reading."
                if context_review else "Read at most 400 lines from one safe source file."
            ),
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
            "description": (
                "Read at most 400 patch lines for one changed file. Line 1 is the +++ header "
                "when present and the first patch line otherwise. These are patch offsets, not source line numbers. "
                "Use totalDiffLines to choose the next range."
            ),
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
        *,
        diff_paths: set[str] | None = None,
    ) -> None:
        self.workspace = workspace
        self.changed_files = changed_files
        self.diff_paths = set(changed_files) if diff_paths is None else diff_paths
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
        self.search_ids: dict[tuple[str, tuple[str, ...], bool, bool, int], int] = {}

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
        range_detail = _requested_range_detail(tool, args)
        try:
            started = self.budget.begin(tool, retrieval_detail=range_detail)
            value = self._execute_allowed_tool(tool, args, started, range_detail)
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
            if isinstance(exception, ReviewToolError) and exception.total_diff_lines is not None:
                error_value["totalDiffLines"] = exception.total_diff_lines
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
            if "totalDiffLines" in error_value:
                range_detail["totalLines"] = error_value["totalDiffLines"]
            self._finish_failed(tool, started, error_code, range_detail)
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
        except Exception as exception:
            if isinstance(exception, OSError):
                range_detail["outcome"] = "IO_ERROR"
            self._finish_failed(tool, started, "INTERNAL_TOOL_ERROR", range_detail)
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
        self, tool: str, args: dict[str, Any], started: float, range_detail: dict[str, Any]
    ) -> dict[str, Any]:
        if tool == "list_files":
            value = self.workspace.list_files(args.get("pattern") or "**/*", args.get("limit") or 200)
            paths = [item["path"] for item in value["files"]]
            self.budget.finish(
                tool, started, item_count=value["count"], paths=paths,
                retrieval_detail=_match_detail(value),
            )
            return value
        if tool == "search_code":
            query = args.get("query")
            globs = args.get("globs")
            is_regex = bool(args.get("isRegex", False))
            case_sensitive = bool(args.get("caseSensitive", True))
            limit = args.get("limit") or 50
            value = self.workspace.search_code(
                query, globs=globs, is_regex=is_regex, case_sensitive=case_sensitive, limit=limit,
            )
            # Store the comparison key in this executor. The audit only carries its ordinal.
            patterns = {str(pattern or "**/*").strip().replace("\\", "/") or "**/*" for pattern in (globs or ["**/*"])}
            search_key = (str(query), tuple(sorted(patterns)), is_regex, case_sensitive, int(limit))
            search_id = self.search_ids.setdefault(search_key, len(self.search_ids) + 1)
            paths = [item["path"] for item in value["matches"]]
            source_bytes = sum(len(item["text"].encode("utf-8")) for item in value["matches"])
            self.budget.finish(
                tool,
                started,
                source_bytes=source_bytes,
                item_count=value["count"],
                paths=paths,
                retrieval_detail={**_match_detail(value), "searchId": search_id},
            )
            return value
        if tool == "read_file_range":
            value = self.workspace.read_file_range(
                args.get("path"), args.get("startLine"), args.get("endLine")
            )
            total_lines = value.pop("totalLines", None)
            self.budget.finish(
                tool,
                started,
                source_bytes=len(value["content"].encode("utf-8")),
                item_count=value["lineCount"],
                paths=[value["path"]],
                retrieval_detail=_returned_range_detail(range_detail, value, total_lines),
            )
            return value
        if tool == "read_diff_range":
            path = str(args.get("path") or "").replace("\\", "/")
            if path not in self.diff_paths:
                raise ReviewToolError("DIFF_PATH_NOT_ALLOWED", "diff path is not a changed file")
            try:
                start_line = int(args.get("startLine") or 0)
                end_line = int(args.get("endLine") or 0)
            except (TypeError, ValueError, OverflowError) as exception:
                raise ReviewToolError("INVALID_ARGUMENT", "diff range must contain 1 to 400 lines") from exception
            if start_line < 1 or end_line < start_line or end_line - start_line + 1 > 400:
                raise ReviewToolError("INVALID_ARGUMENT", "diff range must contain 1 to 400 lines")
            patch = self.diff_by_file.get(path)
            if not patch:
                raise ReviewToolError("DIFF_CONTENT_UNAVAILABLE", "no readable patch is available for this changed file")
            lines = patch.split("\n")
            if start_line > len(lines):
                raise ReviewToolError(
                    "DIFF_RANGE_OUT_OF_BOUNDS",
                    "diff startLine is beyond the end of the patch",
                    total_diff_lines=len(lines),
                )
            selected = lines[start_line - 1 : end_line]
            content = "\n".join(selected)
            value = {
                "path": path,
                "startLine": start_line,
                "endLine": min(end_line, len(lines)),
                "lineCount": len(selected),
                "totalDiffLines": len(lines),
                "content": content,
            }
            self.budget.finish(
                tool,
                started,
                source_bytes=len(content.encode("utf-8")),
                item_count=value["lineCount"],
                paths=[path],
                retrieval_detail=_returned_range_detail(range_detail, value, value["totalDiffLines"]),
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
        started: float | None,
        error_code: str,
        retrieval_detail: dict[str, Any],
    ) -> None:
        if started is None:
            return
        try:
            self.budget.finish(
                tool,
                started,
                status="FAILED",
                error_code=error_code,
                retrieval_detail=retrieval_detail,
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


def _match_detail(value: dict[str, Any]) -> dict[str, Any]:
    detail = {key: value[key] for key in ("timedOut", "truncated") if key in value}
    if value["count"]:
        detail["outcome"] = "RETURNED"
    elif not (detail.get("timedOut") or detail.get("truncated")):
        detail["outcome"] = "NO_MATCH"
    return detail


def _requested_range_detail(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    if tool not in {"read_file_range", "read_diff_range"}:
        return {}
    detail: dict[str, Any] = {
        "coordinateSpace": "DIFF" if tool == "read_diff_range" else "SOURCE",
    }
    for argument, field in (("startLine", "requestedStartLine"), ("endLine", "requestedEndLine")):
        value = args.get(argument)
        if isinstance(value, bool):
            continue
        try:
            detail[field] = int(value)
        except (TypeError, ValueError, OverflowError):
            pass
    return detail


def _returned_range_detail(
    requested: dict[str, Any], value: dict[str, Any], total_lines: int | None
) -> dict[str, Any]:
    detail = dict(requested)
    if total_lines is not None:
        detail["totalLines"] = total_lines
    if value["lineCount"]:
        detail.update(
            outcome="RETURNED", returnedStartLine=value["startLine"], returnedEndLine=value["endLine"]
        )
    elif total_lines is not None and value["startLine"] > total_lines:
        detail["outcome"] = "RANGE_OUT_OF_BOUNDS"
    return detail


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=f".{path.name}."
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        temporary = Path(handle.name)
    os.replace(temporary, path)
