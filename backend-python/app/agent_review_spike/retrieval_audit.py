from __future__ import annotations

from typing import Any

from app.agent_review_spike.budgets import AGENT_BUDGET_LIMITS


EVIDENCE_TOOLS = {"list_files", "search_code", "read_file_range", "read_diff_range"}
_COORDINATE_SPACES = {"read_file_range": "SOURCE", "read_diff_range": "DIFF"}
_MAX_LINE = 10_000_399
_MAX_SEARCH_ID = AGENT_BUDGET_LIMITS["maxToolCalls"]["max"]
_FAILURE_OUTCOMES = {
    "DIFF_CONTENT_UNAVAILABLE": "DIFF_CONTENT_UNAVAILABLE",
    "DIFF_RANGE_OUT_OF_BOUNDS": "RANGE_OUT_OF_BOUNDS",
    "INVALID_ARGUMENT": "INVALID_REQUEST",
    "INVALID_GLOB": "INVALID_REQUEST",
    "INVALID_QUERY": "INVALID_REQUEST",
    "INVALID_REGEX": "INVALID_REQUEST",
    "UNSAFE_REGEX": "ACCESS_DENIED",
    "DIFF_PATH_NOT_ALLOWED": "ACCESS_DENIED",
    "PATH_OUTSIDE_WORKTREE": "ACCESS_DENIED",
    "SENSITIVE_PATH_DENIED": "ACCESS_DENIED",
    "SYMLINK_DENIED": "ACCESS_DENIED",
    "FILE_NOT_FOUND": "ACCESS_DENIED",
    "FILE_TOO_LARGE": "ACCESS_DENIED",
    "BINARY_FILE": "ACCESS_DENIED",
    "EVIDENCE_COLLECTION_COMPLETE": "BUDGET_EXHAUSTED",
    "SOURCE_BUDGET_EXCEEDED": "BUDGET_EXHAUSTED",
}


def retrieval_failure_outcome(error_code: str | None) -> str | None:
    return _FAILURE_OUTCOMES.get(error_code) if error_code else None


def sanitize_retrieval_detail(raw: Any, event: dict[str, Any]) -> dict[str, Any]:
    tool = event["tool"]
    if tool not in EVIDENCE_TOOLS or not isinstance(raw, dict):
        return {}

    detail: dict[str, Any] = {}
    success = event["status"] == "SUCCESS"
    item_count = event["itemCount"]
    if success and tool in {"search_code", "list_files"}:
        flags = ("timedOut", "truncated") if tool == "search_code" else ("truncated",)
        for flag in flags:
            if type(raw.get(flag)) is bool:
                detail[flag] = raw[flag]
        if tool == "search_code":
            search_id = _bounded_int(raw.get("searchId"), 1, _MAX_SEARCH_ID)
            if search_id is not None:
                detail["searchId"] = search_id
    incomplete = detail.get("timedOut") or detail.get("truncated")

    coordinates = _COORDINATE_SPACES.get(tool)
    total = None
    start = None
    if coordinates and raw.get("coordinateSpace") == coordinates:
        detail["coordinateSpace"] = coordinates
        total = _bounded_int(raw.get("totalLines"), 0, _MAX_LINE)
        if total is not None:
            detail["totalLines"] = total
        start = _bounded_int(raw.get("requestedStartLine"), 1, _MAX_LINE)
        end = _bounded_int(raw.get("requestedEndLine"), 1, _MAX_LINE)
        if start is not None and end is not None and 0 <= end - start < 400:
            detail["requestedStartLine"] = start
            detail["requestedEndLine"] = end
        returned_start = _bounded_int(raw.get("returnedStartLine"), 1, _MAX_LINE)
        returned_end = _bounded_int(raw.get("returnedEndLine"), 1, _MAX_LINE)
        if (
            success
            and 1 <= item_count <= 400
            and returned_start is not None
            and returned_end == returned_start + item_count - 1
            and (total is None or returned_end <= total)
            and ("requestedStartLine" not in detail or (returned_start == start and returned_end <= end))
        ):
            detail["returnedStartLine"] = returned_start
            detail["returnedEndLine"] = returned_end

    outcome = raw.get("outcome")
    if success:
        if (outcome == "RETURNED" and item_count > 0) or (
            outcome == "NO_MATCH" and item_count == 0 and not incomplete and not coordinates
        ) or (
            outcome == "RANGE_OUT_OF_BOUNDS"
            and tool == "read_file_range"
            and item_count == 0
            and detail.get("requestedStartLine") is not None
            and start is not None
            and total is not None
            and start > total
        ):
            detail["outcome"] = outcome
    elif isinstance(outcome, str) and (
        outcome == retrieval_failure_outcome(event.get("errorCode"))
        or (outcome == "IO_ERROR" and event.get("errorCode") == "INTERNAL_TOOL_ERROR")
    ):
        if outcome not in {"DIFF_CONTENT_UNAVAILABLE", "RANGE_OUT_OF_BOUNDS"} or tool == "read_diff_range":
            detail["outcome"] = outcome
    return detail


def _bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    return value if type(value) is int and minimum <= value <= maximum else None
