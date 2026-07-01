from __future__ import annotations

from collections import Counter
import json
import re
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.json_utils import read_json_array
from app.deterministic_checks.service import latest_security_summary
from app.project_integration import gitlab_client
from app.review_feedback.models import ReviewItemFeedback
from app.review_feedback.repository import ensure_feedback_schema
from app.review_context.local_repo import prepare_local_repository_context, task_head_worktree_path
from app.review_context.local_retriever import SUPPORTED_REFERENCE_SIGNAL_TYPES, retrieve_local_reference_context


CONTEXT_PACK_VERSION = "context-pack-v0"
CONTEXT_PACK_MAX_TOTAL_CHARS = 6000
CONTEXT_PACK_MAX_CHANGED_FILES = 30
CONTEXT_PACK_MAX_FEEDBACK_BUCKETS = 8
CONTEXT_PACK_MAX_UNAVAILABLE_CONTEXTS = 8
CONTEXT_PACK_MAX_PATH_CHARS = 240
CONTEXT_PACK_MAX_SOURCE_CONTEXT_FILES = 5
CONTEXT_PACK_MAX_SNIPPETS_PER_FILE = 3
CONTEXT_PACK_SOURCE_CONTEXT_WINDOW_LINES = 30
CONTEXT_PACK_MAX_SNIPPET_CHARS = 3500
CONTEXT_PLANNER_VERSION = "context-planner-v0"
CONTEXT_PLANNER_MAX_SIGNALS = 20
CONTEXT_PLANNER_MAX_REQUESTED_CONTEXTS = 16
CONTEXT_PLANNER_MAX_FILE_PATHS_PER_CONTEXT = 8
CONTEXT_PLANNER_MAX_FEEDBACK_CONTEXT_TYPES = 5
RULE_GAP_MAX_ITEMS = 12
HIGH_MISJUDGMENT_SIGNAL_TYPES = {
    "DB_SQL_MAPPER_CHANGED",
    "DTO_FIELD_CHANGED",
    "FIELD_DELETED",
    "METHOD_SIGNATURE_CHANGED",
    "METHOD_DELETED",
}
LOCAL_REFERENCE_MIN_SNIPPETS_PER_HIGH_SIGNAL_SEARCH = 1
NOT_INJECTED_EVIDENCE_MAX_ITEMS = 8


_METHOD_SIGNATURE_PATTERNS = [
    re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\("),
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("),
    re.compile(
        r"^\s*(?:(?:public|private|protected|internal|open|override|suspend|inline|static|final)\s+)*"
        r"fun\s+([A-Za-z_]\w*)\s*\("
    ),
    re.compile(
        r"^\s*(?:(?:public|private|protected|static|final|abstract|synchronized|native|async)\s+)*"
        r"(?:[\w$<>\[\],.?]+\s+)+([A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*(?:\{|throws\b|$)"
    ),
    re.compile(
        r"^\s*(?:(?:public|private|protected|async|static)\s+)*"
        r"([A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*(?::\s*[\w<>\[\]|.?]+\s*)?\{?\s*$"
    ),
]
_CONTROL_METHOD_NAMES = {"if", "for", "while", "switch", "catch", "return", "new"}
_FIELD_PATTERN = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final|readonly|const|let|var)\s+)*"
    r"(?:[A-Za-z_$][\w$<>\[\],.?|]*\s+)?([A-Za-z_$][\w$]*)\??\s*(?::|=|;)"
)
_SQL_PATTERN = re.compile(
    r"\b(select|insert|update|delete|merge|create|alter|drop|truncate|replace|where|join)\b",
    re.IGNORECASE,
)
_SQL_DDL_TABLE_PATTERN = re.compile(
    r"\b(?:create|alter|drop|truncate)\s+table\s+(?:if\s+(?:not\s+)?exists\s+)?[`\"\[]?([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
    re.IGNORECASE,
)
_SQL_TABLE_PATTERN = re.compile(
    r"\b(?:from|join|into|update|table)\s+[`\"\[]?([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
    re.IGNORECASE,
)
_SQL_COLUMN_PATTERN = re.compile(
    r"\b(?:add|drop|modify|change)\s+(?:column\s+)?[`\"\[]?([A-Za-z_][\w$]*)",
    re.IGNORECASE,
)
_SQL_ASSIGNMENT_PATTERN = re.compile(r"\b([A-Za-z_][\w$]*)\s*=", re.IGNORECASE)
_MYBATIS_ID_PATTERN = re.compile(r"\bid\s*=\s*['\"]([A-Za-z_$][\w$]*)['\"]", re.IGNORECASE)
_MYBATIS_PARAM_PATTERN = re.compile(r"[#\$]\{\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)")
_JAVA_CLASS_PATTERN = re.compile(r"\b(?:class|record|interface|enum)\s+([A-Za-z_$][\w$]*)")
_DB_IDENTIFIER_STOP_WORDS = {
    "add",
    "alter",
    "and",
    "as",
    "by",
    "column",
    "constraint",
    "create",
    "default",
    "delete",
    "drop",
    "exists",
    "false",
    "from",
    "group",
    "id",
    "if",
    "index",
    "insert",
    "into",
    "join",
    "key",
    "limit",
    "modify",
    "not",
    "null",
    "namespace",
    "on",
    "or",
    "order",
    "primary",
    "parametertype",
    "resulttype",
    "select",
    "set",
    "table",
    "true",
    "update",
    "values",
    "where",
}
_CACHE_PATTERN = re.compile(
    r"(redis|redisson|cache|caffeine|ehcache|memcache|setex|setnx|expire|evict|invalidate|put|delete|del)",
    re.IGNORECASE,
)
_MQ_PATTERN = re.compile(
    r"\b(kafka|rabbitmq|rocketmq|pulsar|queue|topic|exchange|consumer|producer|listener|group-id|binding)\b",
    re.IGNORECASE,
)
_CONFIG_FILE_SUFFIXES = (
    ".yml",
    ".yaml",
    ".properties",
    ".toml",
    ".ini",
    ".conf",
    ".env",
)


def build_review_context_pack(
    db: Session | None,
    *,
    task_id: int | None = None,
    project_id: int | None,
    changed_files: list[Any] | None,
    diff_text: str | None,
    mode: str | None,
    repository_url: str | None = None,
    git_project_id: str | None = None,
    head_ref: str | None = None,
) -> dict[str, Any]:
    files = _normalize_changed_files(changed_files or [], diff_text)
    feedback_summary = _context_missing_feedback_summary(db, project_id)
    same_file_context, source_unavailable_contexts = _same_file_context(
        files,
        git_project_id=git_project_id,
        head_ref=head_ref,
    )
    context_plan = _context_plan(files, feedback_summary, same_file_context)
    planner_signals = context_plan.pop("_plannerSignals", [])
    requested_contexts = context_plan.pop("_requestedContexts", [])
    planner_unavailable_contexts = context_plan.pop("_unavailableContexts", [])
    local_repository_context = prepare_local_repository_context(
        project_id=project_id,
        task_id=task_id,
        repository_url=repository_url,
        git_project_id=git_project_id,
        head_ref=head_ref,
    )
    local_reference_context = _local_reference_context(
        task_id=task_id,
        local_repository_context=local_repository_context,
        planner_signals=planner_signals,
    )
    local_reference_pack_context = _local_reference_pack_context(local_reference_context)
    _prioritize_local_reference_context(local_reference_pack_context)
    not_injected_evidence = _not_injected_evidence_from_local_reference(local_reference_pack_context)
    _apply_local_reference_availability(requested_contexts, local_reference_pack_context)
    planner_unavailable_contexts = _planner_unavailable_contexts(requested_contexts)
    context_plan["unavailableContextCount"] = len(planner_unavailable_contexts)
    deterministic_checks = {
        "securitySummary": latest_security_summary(db, task_id),
    }
    unavailable_contexts = _unavailable_contexts(
        files,
        source_unavailable_contexts,
        planner_unavailable_contexts,
        local_repository_context.get("unavailableContexts") or [],
        local_reference_context.get("unavailableContexts") or [],
    )
    context_pack = {
        "version": CONTEXT_PACK_VERSION,
        "changedFilesSummary": _changed_files_summary(files, diff_text),
        "sameFileContext": same_file_context,
        "localRepositoryContext": local_repository_context.get("summary") or {},
        "localReferenceSearch": local_reference_pack_context["summary"],
        "localReferenceContext": local_reference_pack_context,
        "deterministicChecks": deterministic_checks,
        "contextPlan": context_plan,
        "plannerSignals": planner_signals,
        "requestedContexts": requested_contexts,
        "contextMissingFeedbackSummary": feedback_summary,
        "unavailableContexts": unavailable_contexts,
        "unavailableContextsTruncated": len(unavailable_contexts) >= CONTEXT_PACK_MAX_UNAVAILABLE_CONTEXTS,
    }
    if not_injected_evidence.get("hasNotInjectedEvidence"):
        context_pack["notInjectedEvidence"] = not_injected_evidence
    review_context = {
        "version": CONTEXT_PACK_VERSION,
        "mode": mode or "DIFF_TEXT",
        "contextPack": context_pack,
    }
    budget_before = _budget_count_snapshot(context_pack)
    prompt_text, truncated_by_budget = _fit_context_pack_budget(context_pack, review_context)
    local_reference_summary = context_pack.get("localReferenceSearch") or _empty_local_reference_summary()
    local_reference_context["summary"] = local_reference_summary
    local_reference_context["searches"] = (context_pack.get("localReferenceContext") or {}).get("searches") or []

    budget_cut_summary = _budget_cut_summary(
        context_pack,
        budget_before,
        prompt_length=len(prompt_text),
        truncated_by_budget=truncated_by_budget,
    )
    observability_summary = _observability_summary(
        planner_signals=planner_signals,
        requested_contexts=requested_contexts,
        local_reference_context=local_reference_context,
        budget_cut_summary=budget_cut_summary,
    )
    context_pack.update(observability_summary)

    meta = {
        "version": CONTEXT_PACK_VERSION,
        "projectId": project_id,
        "mode": mode or "DIFF_TEXT",
        "maxTotalChars": CONTEXT_PACK_MAX_TOTAL_CHARS,
        "promptLength": len(prompt_text),
        "truncated": bool(
            truncated_by_budget
            or context_pack["changedFilesSummary"].get("truncated")
            or context_pack["contextMissingFeedbackSummary"].get("truncated")
            or context_pack["unavailableContextsTruncated"]
        ),
        "changedFileCount": context_pack["changedFilesSummary"]["total"],
        "includedChangedFileCount": context_pack["changedFilesSummary"]["included"],
        "unavailableContextCount": len(context_pack["unavailableContexts"]),
        "contextMissingFeedbackTotal": context_pack["contextMissingFeedbackSummary"]["total"],
        "sameFileSourceSnippetCount": context_pack["sameFileContext"].get("sourceSnippetCount", 0),
        "sameFileSourceFileCount": context_pack["sameFileContext"].get("includedSourceFileCount", 0),
        "plannerSignalCount": context_pack["contextPlan"].get("plannerSignalCount", 0),
        "requestedContextCount": context_pack["contextPlan"].get("requestedContextCount", 0),
        "plannerUnavailableContextCount": context_pack["contextPlan"].get("unavailableContextCount", 0),
        "localRepositoryEnabled": bool(context_pack["localRepositoryContext"].get("enabled")),
        "localRepositoryStatus": context_pack["localRepositoryContext"].get("status"),
        "localReferenceQueryCount": local_reference_summary.get("queryCount", 0),
        "localReferenceMatchedFileCount": local_reference_summary.get("matchedFileCount", 0),
        "localReferenceSnippetCount": local_reference_summary.get("includedSnippetCount", 0),
        "localReferenceTruncated": bool(local_reference_summary.get("truncated", False)),
        "deterministicCheckStatus": deterministic_checks["securitySummary"].get("status"),
        "deterministicCheckFindingCount": deterministic_checks["securitySummary"].get("findingCount", 0),
    }
    return {
        "reviewContext": review_context,
        "contextPack": context_pack,
        "localReferenceRetrieval": local_reference_context,
        "promptText": prompt_text,
        "summary": _progress_summary(context_pack, meta),
        "meta": meta,
    }


def _normalize_changed_files(raw_files: list[Any], diff_text: str | None) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for item in raw_files:
        if isinstance(item, dict):
            path = _clean_path(item.get("path") or item.get("newPath") or item.get("oldPath"))
            if not path:
                continue
            diff = str(item.get("diffText") or "")
            files.append(
                {
                    "path": path,
                    "oldPath": _clean_path(item.get("oldPath")),
                    "newPath": _clean_path(item.get("newPath")),
                    "changeType": _change_type(item),
                    "diffText": diff,
                    "metadataSource": item.get("source"),
                }
            )
            continue
        path = _clean_path(item)
        if path:
            files.append(
                {
                    "path": path,
                    "oldPath": None,
                    "newPath": path,
                    "changeType": "MODIFIED",
                    "diffText": "",
                    "metadataSource": None,
                }
            )
    diff_by_path = _split_diff_by_path(diff_text or "")
    seen_paths = {_normalize_path(file["path"]) for file in files}
    for file in files:
        if not file.get("diffText"):
            file["diffText"] = diff_by_path.get(_normalize_path(file["path"]), "")
    for path, diff in diff_by_path.items():
        if path in seen_paths:
            continue
        files.append(
            {
                "path": path,
                "oldPath": None,
                "newPath": path,
                "changeType": "MODIFIED",
                "diffText": diff,
                "metadataSource": "diffText",
            }
        )
    return files


def _changed_files_summary(files: list[dict[str, Any]], diff_text: str | None) -> dict[str, Any]:
    included_files = files[:CONTEXT_PACK_MAX_CHANGED_FILES]
    return {
        "total": len(files),
        "included": len(included_files),
        "truncated": len(files) > len(included_files),
        "diffBytes": len(diff_text or ""),
        "files": [_file_summary(file) for file in included_files],
    }


def _file_summary(file: dict[str, Any]) -> dict[str, Any]:
    diff = str(file.get("diffText") or "")
    additions, deletions, hunk_count, context_count = _diff_stats(diff)
    return {
        "path": _truncate(str(file.get("path") or ""), CONTEXT_PACK_MAX_PATH_CHARS),
        "oldPath": _truncate(str(file.get("oldPath") or ""), CONTEXT_PACK_MAX_PATH_CHARS) or None,
        "newPath": _truncate(str(file.get("newPath") or ""), CONTEXT_PACK_MAX_PATH_CHARS) or None,
        "changeType": file.get("changeType") or "MODIFIED",
        "diffAvailable": bool(diff.strip()),
        "additions": additions,
        "deletions": deletions,
        "hunkCount": hunk_count,
        "diffContextLineCount": context_count,
    }


def _same_file_context(
    files: list[dict[str, Any]],
    *,
    git_project_id: str | None,
    head_ref: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    files_with_diff = [file for file in files if str(file.get("diffText") or "").strip()]
    files_with_context_lines = [
        file for file in files_with_diff if _diff_stats(str(file.get("diffText") or ""))[3] > 0
    ]
    source_contexts, unavailable = _source_snippets_for_changed_files(
        files_with_diff,
        git_project_id=git_project_id,
        head_ref=head_ref,
    )
    source_file_count = len(source_contexts)
    source_snippet_count = sum(len(item.get("snippets") or []) for item in source_contexts)
    status = "AVAILABLE" if source_snippet_count else ("PARTIAL" if files_with_diff else "UNAVAILABLE")
    available_source = (
        "GITLAB_RAW_FILE_SNIPPETS"
        if source_snippet_count
        else ("DIFF_HUNK_CONTEXT_ONLY" if files_with_diff else "NONE")
    )
    return {
        "status": status,
        "availableSource": available_source,
        "filesWithDiff": len(files_with_diff),
        "filesWithDiffContextLines": len(files_with_context_lines),
        "filesWithoutDiff": max(len(files) - len(files_with_diff), 0),
        "fullFileSourceIncluded": False,
        "sourceSnippetWindowLines": CONTEXT_PACK_SOURCE_CONTEXT_WINDOW_LINES,
        "sourceSnippetCount": source_snippet_count,
        "includedSourceFileCount": source_file_count,
        "candidateSourceFileCount": len(files_with_diff),
        "sourceContextTruncated": (
            len(files_with_diff) > source_file_count
            or any(bool(item.get("truncated")) for item in source_contexts)
        ),
        "sourceSnippets": source_contexts,
        "note": (
            "V0 includes bounded same-file snippets from changed files when GitLab raw file context is available. "
            "It never includes full file source."
        ),
    }, unavailable


def _source_snippets_for_changed_files(
    files: list[dict[str, Any]],
    *,
    git_project_id: str | None,
    head_ref: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not files:
        return [], []
    capability_error = _source_context_capability_error(git_project_id, head_ref)
    if capability_error:
        return [], [capability_error]

    contexts: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for file in files[:CONTEXT_PACK_MAX_SOURCE_CONTEXT_FILES]:
        path = _source_path_for_file(file)
        if not path:
            unavailable.append(
                {
                    "type": "SAME_FILE_CONTEXT",
                    "filePath": str(file.get("path") or "-"),
                    "reason": "Changed file path is unavailable.",
                }
            )
            continue
        if _change_type(file) == "DELETED":
            unavailable.append(
                {
                    "type": "SAME_FILE_CONTEXT",
                    "filePath": path,
                    "reason": "Head source snippet is unavailable for deleted files.",
                }
            )
            continue
        changed_ranges = _changed_new_line_ranges(str(file.get("diffText") or ""))
        if not changed_ranges:
            unavailable.append(
                {
                    "type": "SAME_FILE_CONTEXT",
                    "filePath": path,
                    "reason": "Diff hunk line numbers are unavailable for this file.",
                }
            )
            continue
        try:
            lines = gitlab_client.get_raw_file(str(git_project_id), path, str(head_ref))
        except AppError as exception:
            unavailable.append(
                {
                    "type": "SAME_FILE_CONTEXT",
                    "filePath": path,
                    "reason": str(exception.message),
                }
            )
            continue
        snippets = _snippets_from_lines(lines, changed_ranges)
        if snippets:
            contexts.append(
                {
                    "path": path,
                    "ref": str(head_ref),
                    "language": _language_for_path(path),
                    "snippetCount": len(snippets),
                    "truncated": len(changed_ranges) > len(snippets),
                    "snippets": snippets,
                }
            )
    if len(files) > CONTEXT_PACK_MAX_SOURCE_CONTEXT_FILES:
        unavailable.append(
            {
                "type": "SAME_FILE_CONTEXT",
                "reason": (
                    f"Only the first {CONTEXT_PACK_MAX_SOURCE_CONTEXT_FILES} changed files "
                    "are eligible for same-file source snippets in V2-F-2."
                ),
            }
        )
    return contexts, unavailable


def _source_context_capability_error(
    git_project_id: str | None,
    head_ref: str | None,
) -> dict[str, Any] | None:
    settings = get_settings()
    if not git_project_id:
        return {
            "type": "SAME_FILE_CONTEXT",
            "reason": "GitLab project id is unavailable; same-file source snippets are not fetched.",
        }
    if not head_ref:
        return {
            "type": "SAME_FILE_CONTEXT",
            "reason": "Head ref is unavailable; same-file source snippets are not fetched.",
        }
    if not settings.gitlab_api_enabled:
        return {
            "type": "SAME_FILE_CONTEXT",
            "reason": "GitLab API is disabled; same-file source snippets are not fetched.",
        }
    if not settings.gitlab_base_url.strip():
        return {
            "type": "SAME_FILE_CONTEXT",
            "reason": "GitLab API base-url is missing; same-file source snippets are not fetched.",
        }
    if not settings.gitlab_token.strip():
        return {
            "type": "SAME_FILE_CONTEXT",
            "reason": "GitLab API token is missing; same-file source snippets are not fetched.",
        }
    return None


def _source_path_for_file(file: dict[str, Any]) -> str | None:
    return _clean_path(file.get("newPath") or file.get("path") or file.get("oldPath"))


def _changed_new_line_ranges(diff: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    current_line: int | None = None
    current_start: int | None = None
    current_end: int | None = None
    for line in diff.splitlines():
        if line.startswith("@@"):
            if current_start is not None and current_end is not None:
                ranges.append((current_start, current_end))
            current_line = _new_start_line_from_hunk(line)
            current_start = None
            current_end = None
            continue
        if current_line is None:
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            if current_start is None:
                current_start = current_line
            current_end = current_line
            current_line += 1
            continue
        if line.startswith("-"):
            continue
        if current_start is not None and current_end is not None:
            ranges.append((current_start, current_end))
            current_start = None
            current_end = None
        current_line += 1
    if current_start is not None and current_end is not None:
        ranges.append((current_start, current_end))
    return _merge_line_ranges(ranges)


def _new_start_line_from_hunk(line: str) -> int | None:
    marker = line.split("@@", 2)[1] if "@@" in line else ""
    for part in marker.strip().split():
        if part.startswith("+"):
            start = part[1:].split(",", 1)[0]
            try:
                return max(int(start), 1)
            except ValueError:
                return None
    return None


def _merge_line_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    ordered = sorted((max(start, 1), max(end, start)) for start, end in ranges)
    merged: list[tuple[int, int]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1] + (CONTEXT_PACK_SOURCE_CONTEXT_WINDOW_LINES * 2):
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _snippets_from_lines(lines: list[str], changed_ranges: list[tuple[int, int]]) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    total_lines = len(lines)
    if total_lines <= 0:
        return snippets
    for changed_start, changed_end in changed_ranges[:CONTEXT_PACK_MAX_SNIPPETS_PER_FILE]:
        start = max(changed_start - CONTEXT_PACK_SOURCE_CONTEXT_WINDOW_LINES, 1)
        end = min(changed_end + CONTEXT_PACK_SOURCE_CONTEXT_WINDOW_LINES, total_lines)
        if end < start:
            continue
        line_items = [
            {"number": number, "text": lines[number - 1]}
            for number in range(start, end + 1)
        ]
        snippet = {
            "startLine": start,
            "endLine": end,
            "changedStartLine": changed_start,
            "changedEndLine": changed_end,
            "reason": "CHANGED_LINES_WINDOW",
            "truncated": False,
            "lines": line_items,
        }
        _truncate_snippet(snippet)
        snippets.append(snippet)
    return snippets


def _truncate_snippet(snippet: dict[str, Any]) -> None:
    while len(json.dumps(snippet, ensure_ascii=False, separators=(",", ":"))) > CONTEXT_PACK_MAX_SNIPPET_CHARS:
        lines = snippet.get("lines") or []
        if len(lines) <= 1:
            break
        lines.pop()
        snippet["lines"] = lines
        snippet["endLine"] = lines[-1]["number"]
        snippet["truncated"] = True


def _context_missing_feedback_summary(db: Session | None, project_id: int | None) -> dict[str, Any]:
    if db is None or project_id is None:
        return {
            "projectId": project_id,
            "total": 0,
            "byRiskType": [],
            "byMissingContextType": [],
            "truncated": False,
        }
    ensure_feedback_schema(db)
    filters = [
        ReviewItemFeedback.project_id == project_id,
        ReviewItemFeedback.reason_type == "CONTEXT_MISSING",
    ]
    total = db.scalar(select(func.count()).select_from(ReviewItemFeedback).where(and_(*filters))) or 0
    risk_rows = db.execute(
        select(ReviewItemFeedback.risk_type, func.count())
        .select_from(ReviewItemFeedback)
        .where(and_(*filters))
        .group_by(ReviewItemFeedback.risk_type)
        .order_by(func.count().desc())
        .limit(CONTEXT_PACK_MAX_FEEDBACK_BUCKETS + 1)
    ).all()
    context_type_counter: Counter[str] = Counter()
    for (raw_types,) in db.execute(
        select(ReviewItemFeedback.missing_context_types_json)
        .select_from(ReviewItemFeedback)
        .where(and_(*filters))
    ).all():
        for item in read_json_array(raw_types):
            if item:
                context_type_counter[str(item)] += 1
    missing_type_items = context_type_counter.most_common(CONTEXT_PACK_MAX_FEEDBACK_BUCKETS + 1)
    return {
        "projectId": project_id,
        "total": int(total),
        "byRiskType": [
            {"riskType": risk_type or "UNKNOWN", "count": int(count)}
            for risk_type, count in risk_rows[:CONTEXT_PACK_MAX_FEEDBACK_BUCKETS]
        ],
        "byMissingContextType": [
            {"missingContextType": item, "count": int(count)}
            for item, count in missing_type_items[:CONTEXT_PACK_MAX_FEEDBACK_BUCKETS]
        ],
        "truncated": (
            len(risk_rows) > CONTEXT_PACK_MAX_FEEDBACK_BUCKETS
            or len(missing_type_items) > CONTEXT_PACK_MAX_FEEDBACK_BUCKETS
        ),
    }


def _context_plan(
    files: list[dict[str, Any]],
    feedback_summary: dict[str, Any],
    same_file_context: dict[str, Any],
) -> dict[str, Any]:
    raw_signals: list[dict[str, Any]] = []
    for file in files:
        raw_signals.extend(_planner_signals_for_file(file))
    raw_signals.extend(_planner_signals_from_feedback(feedback_summary))

    signals = raw_signals[:CONTEXT_PLANNER_MAX_SIGNALS]
    requested_contexts = _requested_contexts_from_signals(signals, same_file_context)
    unavailable_contexts = _planner_unavailable_contexts(requested_contexts)
    requested_context_type_counts = [
        {"type": item["type"], "count": int(item.get("signalCount") or 0)}
        for item in requested_contexts
    ]
    return {
        "version": CONTEXT_PLANNER_VERSION,
        "plannerSignalCount": len(signals),
        "plannerSignalTotal": len(raw_signals),
        "plannerSignalsTruncated": len(raw_signals) > len(signals),
        "requestedContextCount": len(requested_contexts),
        "requestedContextTypeCounts": requested_context_type_counts,
        "unavailableContextCount": len(unavailable_contexts),
        "budget": {
            "maxSignals": CONTEXT_PLANNER_MAX_SIGNALS,
            "maxRequestedContexts": CONTEXT_PLANNER_MAX_REQUESTED_CONTEXTS,
            "maxFilePathsPerContext": CONTEXT_PLANNER_MAX_FILE_PATHS_PER_CONTEXT,
        },
        "note": (
            "Advisory only; no project scan, reference search, RAG, auto-ignore, or auto-downgrade."
        ),
        "_plannerSignals": signals,
        "_requestedContexts": requested_contexts,
        "_unavailableContexts": unavailable_contexts,
    }


def _planner_signals_for_file(file: dict[str, Any]) -> list[dict[str, Any]]:
    diff = str(file.get("diffText") or "")
    path = str(file.get("path") or "")
    added_lines, deleted_lines = _changed_line_bodies(diff)
    changed_lines = [*added_lines, *deleted_lines]
    signals: list[dict[str, Any]] = []

    deleted_methods = _method_names(deleted_lines)
    added_methods = _method_names(added_lines)
    signature_changed = sorted(set(deleted_methods) & set(added_methods))
    method_deleted = sorted(set(deleted_methods) - set(added_methods))
    if method_deleted:
        signals.append(
            _planner_signal(
                "METHOD_DELETED",
                file,
                ["REFERENCE_SEARCH", "CALLER_CONTEXT", "SAME_CLASS_METHODS", "TEST_RESULT_CONTEXT"],
                priority="HIGH",
                details={"methodNames": method_deleted[:5], "methodCount": len(method_deleted)},
            )
        )
    if signature_changed:
        signals.append(
            _planner_signal(
                "METHOD_SIGNATURE_CHANGED",
                file,
                ["REFERENCE_SEARCH", "CALLER_CONTEXT", "CALLEE_CONTEXT", "TEST_RESULT_CONTEXT"],
                priority="HIGH",
                details={"methodNames": signature_changed[:5], "methodCount": len(signature_changed)},
            )
        )

    deleted_fields = _field_names(deleted_lines)
    added_fields = _field_names(added_lines)
    field_deleted = sorted(set(deleted_fields) - set(added_fields))
    if field_deleted:
        signals.append(
            _planner_signal(
                "FIELD_DELETED",
                file,
                ["REFERENCE_SEARCH", "CALLER_CONTEXT", "TEST_RESULT_CONTEXT"],
                priority="MEDIUM",
                details={"fieldNames": field_deleted[:8], "fieldCount": len(field_deleted)},
            )
        )
    if _is_dto_path(path) and (deleted_fields or added_fields):
        changed_fields = sorted(set(deleted_fields) | set(added_fields))
        signals.append(
            _planner_signal(
                "DTO_FIELD_CHANGED",
                file,
                ["REFERENCE_SEARCH", "CALLER_CONTEXT", "RELATED_FILE", "TEST_RESULT_CONTEXT"],
                priority="HIGH",
                details={"fieldNames": changed_fields[:8], "fieldCount": len(changed_fields)},
            )
        )

    if _is_db_or_mapper_change(path, changed_lines):
        signals.append(
            _planner_signal(
                "DB_SQL_MAPPER_CHANGED",
                file,
                ["DB_SCHEMA_CONTEXT", "RELATED_FILE", "TEST_RESULT_CONTEXT"],
                priority="HIGH",
                details=_db_signal_details(file, changed_lines),
            )
        )
    if _has_cache_write_delete_change(path, changed_lines):
        signals.append(
            _planner_signal(
                "CACHE_WRITE_DELETE_CHANGED",
                file,
                ["CACHE_USAGE_CONTEXT", "REFERENCE_SEARCH", "TEST_RESULT_CONTEXT"],
                priority="HIGH",
            )
        )
    if _is_mq_config_change(path, changed_lines):
        signals.append(
            _planner_signal(
                "MQ_CONFIG_CHANGED",
                file,
                ["MQ_CONFIG_CONTEXT", "CONFIG_CONTEXT", "TEST_RESULT_CONTEXT"],
                priority="HIGH",
            )
        )
    if _is_config_file_change(path, changed_lines):
        signals.append(
            _planner_signal(
                "CONFIG_FILE_CHANGED",
                file,
                ["CONFIG_CONTEXT", "TEST_RESULT_CONTEXT"],
                priority="MEDIUM",
            )
        )
    return signals


def _planner_signal(
    signal_type: str,
    file: dict[str, Any],
    requested_context_types: list[str],
    *,
    priority: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = _truncate(str(file.get("path") or ""), CONTEXT_PACK_MAX_PATH_CHARS)
    signal = {
        "type": signal_type,
        "priority": priority,
        "filePath": path,
        "requestedContextTypes": requested_context_types,
    }
    if details:
        signal["details"] = details
    return signal


def _planner_signals_from_feedback(feedback_summary: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for item in (feedback_summary.get("byMissingContextType") or [])[:CONTEXT_PLANNER_MAX_FEEDBACK_CONTEXT_TYPES]:
        context_type = str(item.get("missingContextType") or "").strip().upper()
        if not context_type:
            continue
        signals.append(
            {
                "type": "HISTORICAL_CONTEXT_MISSING_FEEDBACK",
                "priority": "MEDIUM",
                "requestedContextTypes": [context_type],
                "details": {"missingContextType": context_type, "feedbackCount": int(item.get("count") or 0)},
            }
        )
    return signals


def _requested_contexts_from_signals(
    signals: list[dict[str, Any]],
    same_file_context: dict[str, Any],
) -> list[dict[str, Any]]:
    requested: dict[str, dict[str, Any]] = {}
    for signal in signals:
        priority = str(signal.get("priority") or "MEDIUM")
        file_path = signal.get("filePath")
        for context_type in signal.get("requestedContextTypes") or []:
            normalized_type = str(context_type or "").strip().upper()
            if not normalized_type:
                continue
            item = requested.setdefault(
                normalized_type,
                {
                    "type": normalized_type,
                    "priority": priority,
                    "filePaths": [],
                    "signalCount": 0,
                    "available": _planner_context_available(normalized_type, same_file_context),
                },
            )
            item["priority"] = _higher_priority(item["priority"], priority)
            item["signalCount"] += 1
            if file_path and file_path not in item["filePaths"]:
                item["filePaths"].append(file_path)
    for item in requested.values():
        item["filePaths"] = item["filePaths"][:CONTEXT_PLANNER_MAX_FILE_PATHS_PER_CONTEXT]
    ordered = sorted(
        requested.values(),
        key=lambda item: (
            -_priority_rank(item.get("priority")),
            -int(item.get("signalCount") or 0),
            str(item.get("type") or ""),
        ),
    )
    return ordered[:CONTEXT_PLANNER_MAX_REQUESTED_CONTEXTS]


def _planner_unavailable_contexts(requested_contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unavailable = []
    for item in requested_contexts:
        if item.get("available"):
            continue
        context_type = str(item.get("type") or "")
        unavailable.append(
            {
                "type": context_type,
                "reason": _unavailable_reason_for_requested_context(context_type),
                "requestedByPlanner": True,
            }
        )
    return unavailable


def _changed_line_bodies(diff: str) -> tuple[list[str], list[str]]:
    added: list[str] = []
    deleted: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            body = line[1:].strip()
            if body:
                added.append(body)
            continue
        if line.startswith("-"):
            body = line[1:].strip()
            if body:
                deleted.append(body)
    return added, deleted


def _method_names(lines: list[str]) -> list[str]:
    names = []
    for line in lines:
        if line.startswith(("@", "//", "#", "*")) or "(" not in line:
            continue
        for pattern in _METHOD_SIGNATURE_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            name = str(match.group(1) or "").strip()
            if name and name.lower() not in _CONTROL_METHOD_NAMES:
                names.append(name)
            break
    return names


def _field_names(lines: list[str]) -> list[str]:
    names = []
    for line in lines:
        if line.startswith(("@", "//", "#", "*")) or "(" in line:
            continue
        match = _FIELD_PATTERN.search(line)
        if not match:
            continue
        name = str(match.group(1) or "").strip()
        if name and name.lower() not in _CONTROL_METHOD_NAMES:
            names.append(name)
    return names


def _is_dto_path(path: str) -> bool:
    lower = _normalize_path(path).lower()
    name = lower.rsplit("/", 1)[-1]
    return any(token in lower for token in ("/dto/", "/vo/", "/request/", "/response/", "/payload/")) or any(
        token in name for token in ("dto", "vo", "request", "response", "payload", "form")
    )


def _is_db_or_mapper_change(path: str, changed_lines: list[str]) -> bool:
    lower = _normalize_path(path).lower()
    if lower.endswith(".sql") or "/mapper/" in lower or lower.endswith("mapper.xml"):
        return True
    if any(token in lower for token in ("/migration/", "/migrations/", "/db/", "/sql/")):
        return True
    if any(token in lower for token in ("entity", "repository", "dao", "mapper")) and _SQL_PATTERN.search(
        "\n".join(changed_lines)
    ):
        return True
    return bool(_SQL_PATTERN.search("\n".join(changed_lines)) and "mapper" in lower)


def _db_signal_details(file: dict[str, Any], changed_lines: list[str]) -> dict[str, Any]:
    path = str(file.get("path") or "")
    line_text = "\n".join(changed_lines)
    table_names = _db_table_names(line_text)
    field_names = _db_field_names(path, changed_lines, line_text)
    mapper_method_names = _db_mapper_method_names(path, changed_lines, line_text)
    entity_names = _db_entity_names(path, changed_lines, line_text)
    return {
        "tableNames": table_names[:8],
        "tableCount": len(table_names),
        "fieldNames": field_names[:10],
        "fieldCount": len(field_names),
        "mapperMethodNames": mapper_method_names[:8],
        "mapperMethodCount": len(mapper_method_names),
        "entityNames": entity_names[:6],
        "entityCount": len(entity_names),
    }


def _db_table_names(line_text: str) -> list[str]:
    candidates = []
    for pattern in (_SQL_DDL_TABLE_PATTERN, _SQL_TABLE_PATTERN):
        for match in pattern.finditer(line_text):
            candidates.append(str(match.group(1) or ""))
    return _normalized_db_identifiers(candidates)


def _db_field_names(path: str, changed_lines: list[str], line_text: str) -> list[str]:
    candidates: list[str] = []
    candidates.extend(_field_names(changed_lines))
    for pattern in (_SQL_COLUMN_PATTERN, _SQL_ASSIGNMENT_PATTERN):
        candidates.extend(str(match.group(1) or "") for match in pattern.finditer(line_text))
    for match in _MYBATIS_PARAM_PATTERN.finditer(line_text):
        candidate = str(match.group(1) or "").rsplit(".", 1)[-1]
        candidates.append(candidate)
    lower_path = _normalize_path(path).lower()
    if any(token in lower_path for token in ("entity", "model", "po", "do")):
        candidates.extend(_field_names(changed_lines))
    return _normalized_db_identifiers(candidates)


def _db_mapper_method_names(path: str, changed_lines: list[str], line_text: str) -> list[str]:
    candidates = [str(match.group(1) or "") for match in _MYBATIS_ID_PATTERN.finditer(line_text)]
    lower_path = _normalize_path(path).lower()
    if any(token in lower_path for token in ("mapper", "repository", "dao")):
        candidates.extend(_method_names(changed_lines))
    return _normalized_db_identifiers(candidates)


def _db_entity_names(path: str, changed_lines: list[str], line_text: str) -> list[str]:
    candidates = [str(match.group(1) or "") for match in _JAVA_CLASS_PATTERN.finditer(line_text)]
    name = _normalize_path(path).rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if any(token in _normalize_path(path).lower() for token in ("entity", "model", "/po/", "/do/")):
        candidates.append(name)
    return _normalized_db_identifiers(candidates)


def _normalized_db_identifiers(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip().strip("`\"[]")
        if "." in text:
            text = text.rsplit(".", 1)[-1]
        if not text:
            continue
        if text.lower() in _DB_IDENTIFIER_STOP_WORDS:
            continue
        if text not in result:
            result.append(text)
    return result


def _has_cache_write_delete_change(path: str, changed_lines: list[str]) -> bool:
    lower_path = _normalize_path(path).lower()
    cacheish_path = any(token in lower_path for token in ("cache", "redis", "redisson", "caffeine", "ehcache"))
    write_verbs = ("set(", ".set", "put(", ".put", "delete(", ".delete", "del(", ".del", "expire(", "evict", "invalidate")
    for line in changed_lines:
        lower = line.lower()
        if "@cacheput" in lower or "@cacheevict" in lower:
            return True
        if (cacheish_path or _CACHE_PATTERN.search(lower)) and any(verb in lower for verb in write_verbs):
            return True
    return False


def _is_mq_config_change(path: str, changed_lines: list[str]) -> bool:
    lower_path = _normalize_path(path).lower()
    path_match = any(token in lower_path for token in ("mq", "kafka", "rabbit", "rocketmq", "pulsar"))
    line_text = "\n".join(changed_lines)
    if path_match and (_is_config_file_change(path, changed_lines) or _MQ_PATTERN.search(line_text)):
        return True
    return bool(_MQ_PATTERN.search(line_text) and _is_config_file_change(path, changed_lines))


def _is_config_file_change(path: str, changed_lines: list[str]) -> bool:
    lower = _normalize_path(path).lower()
    name = lower.rsplit("/", 1)[-1]
    if lower.endswith(_CONFIG_FILE_SUFFIXES):
        return True
    if name in {"application.json", "bootstrap.json", "settings.json"}:
        return True
    if any(token in lower for token in ("/config/", "/nacos/", "/resources/")) and name.endswith(".json"):
        return True
    return any("@value" in line.lower() or "@configurationproperties" in line.lower() for line in changed_lines)


def _planner_context_available(context_type: str, same_file_context: dict[str, Any]) -> bool:
    if context_type == "SAME_FILE_CONTEXT":
        return str(same_file_context.get("status") or "").upper() in {"AVAILABLE", "PARTIAL"}
    return False


def _unavailable_reason_for_requested_context(context_type: str) -> str:
    return {
        "REFERENCE_SEARCH": "Local reference snippets are unavailable.",
        "CALLER_CONTEXT": "Caller inspection beyond reference snippets is not performed.",
        "CALLEE_CONTEXT": "Callee inspection is not performed.",
        "SAME_CLASS_METHODS": "Class parsing is not performed.",
        "RELATED_FILE": "Related files are not read.",
        "DB_SCHEMA_CONTEXT": "DB / Mapper / Entity relation snippets are unavailable.",
        "CONFIG_CONTEXT": "Runtime config is not retrieved.",
        "MQ_CONFIG_CONTEXT": "MQ config is not retrieved.",
        "CACHE_USAGE_CONTEXT": "Cache usages are not searched.",
        "TEST_RESULT_CONTEXT": "Tests are not executed.",
    }.get(context_type, "Unavailable in V2-F-6.")


def _higher_priority(current: str, candidate: str) -> str:
    return candidate if _priority_rank(candidate) > _priority_rank(current) else current


def _priority_rank(priority: Any) -> int:
    return {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(str(priority or "").upper(), 0)


def _unavailable_contexts(
    files: list[dict[str, Any]],
    source_unavailable_contexts: list[dict[str, Any]],
    planner_unavailable_contexts: list[dict[str, Any]],
    local_repo_unavailable_contexts: list[dict[str, Any]],
    local_reference_unavailable_contexts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contexts = [
        {
            "type": "SAME_FILE_FULL_SOURCE",
            "reason": "Only bounded snippets are included; full source is excluded.",
        },
        {
            "type": "REFERENCE_SEARCH",
            "reason": "Reference, caller, DB / Mapper / Entity, and usage search is not performed.",
        },
        {
            "type": "CALLER_CONTEXT",
            "reason": "Callers outside the changed diff are not inspected.",
        },
        {
            "type": "CALLEE_CONTEXT",
            "reason": "Callees outside the changed diff are not inspected.",
        },
        {
            "type": "RELATED_FILE",
            "reason": "Related files are only available when bounded local relation snippets are retrieved.",
        },
        {
            "type": "DB_SCHEMA_CONTEXT",
            "reason": "Database schema is only inferred from bounded SQL / Mapper / Entity snippets; runtime DB is not queried.",
        },
        {
            "type": "CONFIG_CONTEXT",
            "reason": "Runtime config outside the diff is not retrieved.",
        },
        {
            "type": "TEST_RESULT_CONTEXT",
            "reason": "Tests are not executed.",
        },
    ]
    if any(not str(file.get("diffText") or "").strip() for file in files):
        contexts.insert(
            1,
            {
                "type": "DIFF_TEXT_FOR_SOME_FILES",
                "reason": "Some changed files have path metadata only.",
            },
        )
    result = []
    seen = set()
    for item in [
        *local_repo_unavailable_contexts,
        *local_reference_unavailable_contexts,
        *planner_unavailable_contexts,
        *source_unavailable_contexts,
        *contexts,
    ]:
        key = (item.get("type"), item.get("filePath"), item.get("reason"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result[:CONTEXT_PACK_MAX_UNAVAILABLE_CONTEXTS]


def _fit_context_pack_budget(
    context_pack: dict[str, Any],
    review_context: dict[str, Any],
) -> tuple[str, bool]:
    prompt_text = _render_context_pack_text(review_context)
    truncated_by_budget = False
    while len(prompt_text) > CONTEXT_PACK_MAX_TOTAL_CHARS:
        if _remove_empty_local_reference_context(context_pack):
            truncated_by_budget = True
            prompt_text = _render_context_pack_text(review_context)
            continue
        if _remove_last_local_reference_snippet(context_pack, protect_high_priority=True):
            truncated_by_budget = True
            prompt_text = _render_context_pack_text(review_context)
            continue
        if _remove_last_source_snippet(context_pack):
            truncated_by_budget = True
            prompt_text = _render_context_pack_text(review_context)
            continue
        if context_pack["changedFilesSummary"]["files"]:
            context_pack["changedFilesSummary"]["files"].pop()
            context_pack["changedFilesSummary"]["included"] = len(context_pack["changedFilesSummary"]["files"])
            context_pack["changedFilesSummary"]["truncated"] = True
            truncated_by_budget = True
            prompt_text = _render_context_pack_text(review_context)
            continue
        if _remove_last_unavailable_context(context_pack):
            truncated_by_budget = True
            prompt_text = _render_context_pack_text(review_context)
            continue
        if _remove_last_requested_context(context_pack):
            truncated_by_budget = True
            prompt_text = _render_context_pack_text(review_context)
            continue
        if _shrink_last_local_reference_snippet(context_pack):
            truncated_by_budget = True
            prompt_text = _render_context_pack_text(review_context)
            continue
        if _remove_last_local_reference_search_metadata(context_pack, protect_high_priority=True):
            truncated_by_budget = True
            prompt_text = _render_context_pack_text(review_context)
            continue
        if _remove_last_local_reference_snippet(context_pack, protect_high_priority=False):
            truncated_by_budget = True
            prompt_text = _render_context_pack_text(review_context)
            continue
        break
    return prompt_text, truncated_by_budget


def _remove_empty_local_reference_context(context_pack: dict[str, Any]) -> bool:
    local_reference = context_pack.get("localReferenceContext") or {}
    if not local_reference:
        return False
    summary = local_reference.get("summary") or {}
    if int(summary.get("includedSnippetCount") or 0) > 0:
        return False
    searches = [item for item in (local_reference.get("searches") or []) if isinstance(item, dict)]
    if any(
        item.get("query")
        or int(item.get("matchedFileCount") or 0) > 0
        or int(item.get("candidateSnippetCount") or 0) > 0
        or bool(item.get("truncated"))
        for item in searches
    ):
        return False
    context_pack.pop("localReferenceContext", None)
    if int((context_pack.get("localReferenceSearch") or {}).get("queryCount") or 0) <= 0:
        context_pack.pop("localReferenceSearch", None)
    return True


def _remove_last_local_reference_snippet(
    context_pack: dict[str, Any],
    *,
    protect_high_priority: bool,
) -> bool:
    local_reference = context_pack.get("localReferenceContext") or {}
    searches = local_reference.get("searches") or []
    for search in reversed([item for item in searches if isinstance(item, dict)]):
        snippets = search.get("snippets") or []
        if snippets:
            if (
                protect_high_priority
                and _is_budget_protected_reference_search(search)
                and len(snippets) <= LOCAL_REFERENCE_MIN_SNIPPETS_PER_HIGH_SIGNAL_SEARCH
            ):
                continue
            snippets.pop()
            search["snippets"] = snippets
            search["includedSnippetCount"] = len(snippets)
            search["truncated"] = True
            _record_not_injected_local_reference(
                context_pack,
                search,
                cut_snippet_count=1,
                reason=(
                    "CONTEXT_PACK_PROMPT_BUDGET_LAST_RESORT"
                    if _is_budget_protected_reference_search(search) and not protect_high_priority
                    else "CONTEXT_PACK_PROMPT_BUDGET"
                ),
            )
            _sync_local_reference_summary(context_pack, truncated=True)
            return True
    return False


def _remove_last_source_snippet(context_pack: dict[str, Any]) -> bool:
    same_file = context_pack.get("sameFileContext") or {}
    source_contexts = same_file.get("sourceSnippets") or []
    while source_contexts:
        last_context = source_contexts[-1]
        snippets = last_context.get("snippets") or []
        if snippets:
            snippets.pop()
            last_context["snippets"] = snippets
            last_context["snippetCount"] = len(snippets)
            last_context["truncated"] = True
            same_file["sourceSnippetCount"] = max(int(same_file.get("sourceSnippetCount") or 0) - 1, 0)
            same_file["sourceContextTruncated"] = True
            if not snippets:
                source_contexts.pop()
                same_file["includedSourceFileCount"] = max(
                    int(same_file.get("includedSourceFileCount") or 0) - 1,
                    0,
                )
            same_file["sourceSnippets"] = source_contexts
            if not source_contexts and same_file.get("filesWithDiff"):
                same_file["status"] = "PARTIAL"
                same_file["availableSource"] = "DIFF_HUNK_CONTEXT_ONLY"
            return True
        source_contexts.pop()
    same_file["sourceSnippets"] = source_contexts
    return False


def _remove_last_unavailable_context(context_pack: dict[str, Any]) -> bool:
    unavailable_contexts = context_pack.get("unavailableContexts") or []
    if not unavailable_contexts:
        return False
    unavailable_contexts.pop()
    context_pack["unavailableContexts"] = unavailable_contexts
    context_pack["unavailableContextsTruncated"] = True
    return True


def _remove_last_requested_context(context_pack: dict[str, Any]) -> bool:
    requested_contexts = context_pack.get("requestedContexts") or []
    if len(requested_contexts) <= 1:
        return False
    removable_index = next(
        (
            index
            for index in range(len(requested_contexts) - 1, -1, -1)
            if str((requested_contexts[index] or {}).get("type") or "").upper() != "REFERENCE_SEARCH"
        ),
        None,
    )
    if removable_index is None:
        return False
    requested_contexts.pop(removable_index)
    context_pack["requestedContexts"] = requested_contexts
    context_plan = context_pack.get("contextPlan") or {}
    context_plan["requestedContextsTrimmedByBudget"] = True
    context_pack["contextPlan"] = context_plan
    return True


def _shrink_last_local_reference_snippet(context_pack: dict[str, Any]) -> bool:
    local_reference = context_pack.get("localReferenceContext") or {}
    searches = [item for item in (local_reference.get("searches") or []) if isinstance(item, dict)]
    for search in reversed(searches):
        for snippet in reversed([item for item in (search.get("snippets") or []) if isinstance(item, dict)]):
            if _shrink_snippet_lines(snippet):
                search["truncated"] = True
                _sync_local_reference_summary(context_pack, truncated=True)
                return True
    return False


def _remove_last_local_reference_search_metadata(
    context_pack: dict[str, Any],
    *,
    protect_high_priority: bool,
) -> bool:
    local_reference = context_pack.get("localReferenceContext") or {}
    searches = [item for item in (local_reference.get("searches") or []) if isinstance(item, dict)]
    for index in range(len(searches) - 1, -1, -1):
        search = searches[index]
        if protect_high_priority and _is_budget_protected_reference_search(search):
            continue
        cut_snippet_count = int(search.get("includedSnippetCount") or 0)
        if cut_snippet_count > 0:
            _record_not_injected_local_reference(
                context_pack,
                search,
                cut_snippet_count=cut_snippet_count,
                reason="CONTEXT_PACK_PROMPT_BUDGET",
            )
        searches.pop(index)
        local_reference["searches"] = searches
        _sync_local_reference_summary(context_pack, truncated=True)
        return True
    return False


def _shrink_snippet_lines(snippet: dict[str, Any]) -> bool:
    lines = [item for item in (snippet.get("lines") or []) if isinstance(item, dict)]
    if len(lines) <= 1:
        return False
    try:
        match_line = int(snippet.get("matchLine") or 0)
    except (TypeError, ValueError):
        match_line = 0
    first_number = int(lines[0].get("number") or 0)
    last_number = int(lines[-1].get("number") or 0)
    if first_number != match_line and abs(first_number - match_line) >= abs(last_number - match_line):
        lines.pop(0)
    elif last_number != match_line:
        lines.pop()
    else:
        lines.pop(0)
    snippet["lines"] = lines
    snippet["startLine"] = int(lines[0].get("number") or snippet.get("startLine") or 1)
    snippet["endLine"] = int(lines[-1].get("number") or snippet.get("endLine") or snippet["startLine"])
    snippet["truncated"] = True
    return True


def _render_context_pack_text(review_context: dict[str, Any]) -> str:
    return json.dumps(review_context, ensure_ascii=False, separators=(",", ":"))


def _progress_summary(context_pack: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    changed = context_pack["changedFilesSummary"]
    same_file = context_pack["sameFileContext"]
    local_repository = context_pack.get("localRepositoryContext") or {}
    local_reference = context_pack.get("localReferenceSearch") or {}
    feedback = context_pack["contextMissingFeedbackSummary"]
    context_plan = context_pack["contextPlan"]
    return {
        "version": meta["version"],
        "projectId": meta.get("projectId"),
        "changedFileCount": changed["total"],
        "includedChangedFileCount": changed["included"],
        "diffBytes": changed["diffBytes"],
        "sameFileContextStatus": same_file["status"],
        "filesWithDiff": same_file["filesWithDiff"],
        "filesWithoutDiff": same_file["filesWithoutDiff"],
        "sameFileSourceSnippetCount": same_file.get("sourceSnippetCount", 0),
        "sameFileSourceFileCount": same_file.get("includedSourceFileCount", 0),
        "localRepository": _local_repository_progress_summary(local_repository),
        "localReferenceSearch": _local_reference_progress_summary(local_reference),
        "deterministicChecks": {
            "securitySummary": context_pack.get("deterministicChecks", {}).get("securitySummary") or {},
        },
        "contextMissingFeedbackTotal": feedback["total"],
        "topMissingContextTypes": feedback["byMissingContextType"][:3],
        "plannerSignalCount": context_plan.get("plannerSignalCount", 0),
        "plannerSignalTotal": context_plan.get("plannerSignalTotal", 0),
        "plannerSignalTypeCounts": (context_pack.get("plannerSignalTypeCounts") or [])[:12],
        "requestedContextCount": context_plan.get("requestedContextCount", 0),
        "requestedContextTypeCounts": context_plan.get("requestedContextTypeCounts", [])[:8],
        "retrieverSupportedSignalTypes": context_pack.get("retrieverSupportedSignalTypes") or [],
        "retrieverUnsupportedSignalTypeCounts": (context_pack.get("retrieverUnsupportedSignalTypeCounts") or [])[:12],
        "requestedContextAvailability": context_pack.get("requestedContextAvailability") or {},
        "budgetCutSummary": context_pack.get("budgetCutSummary") or {},
        "ruleGapSummary": context_pack.get("ruleGapSummary") or {},
        "ruleGapItems": (context_pack.get("ruleGapItems") or [])[:RULE_GAP_MAX_ITEMS],
        "plannerUnavailableContextCount": context_plan.get("unavailableContextCount", 0),
        "unavailableContextCount": meta["unavailableContextCount"],
        "promptLength": meta["promptLength"],
        "truncated": meta["truncated"],
    }


def _local_repository_progress_summary(local_repository: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "enabled": bool(local_repository.get("enabled")),
        "status": local_repository.get("status"),
        "projectId": local_repository.get("projectId"),
        "taskId": local_repository.get("taskId"),
        "headRef": local_repository.get("headRef"),
        "mirrorStatus": local_repository.get("mirrorStatus"),
        "worktreeStatus": local_repository.get("worktreeStatus"),
        "failurePhase": local_repository.get("failurePhase"),
        "durationMs": local_repository.get("durationMs"),
        "sourceIncluded": bool(local_repository.get("sourceIncluded", False)),
    }
    cleanup = _local_repository_cleanup_progress_summary(local_repository.get("cleanup"))
    if cleanup:
        summary["cleanup"] = cleanup
    return summary


def _local_repository_cleanup_progress_summary(cleanup: Any) -> dict[str, Any] | None:
    if not isinstance(cleanup, dict):
        return None
    return {
        "enabled": bool(cleanup.get("enabled")),
        "status": cleanup.get("status"),
        "worktreeRetentionHours": int(cleanup.get("worktreeRetentionHours") or 0),
        "mirrorRetentionDays": int(cleanup.get("mirrorRetentionDays") or 0),
        "scannedWorktreeCount": int(cleanup.get("scannedWorktreeCount") or 0),
        "deletedWorktreeCount": int(cleanup.get("deletedWorktreeCount") or 0),
        "skippedWorktreeCount": int(cleanup.get("skippedWorktreeCount") or 0),
        "scannedMirrorCount": int(cleanup.get("scannedMirrorCount") or 0),
        "deletedMirrorCount": int(cleanup.get("deletedMirrorCount") or 0),
        "skippedMirrorCount": int(cleanup.get("skippedMirrorCount") or 0),
        "bytesDeleted": int(cleanup.get("bytesDeleted") or 0),
        "durationMs": int(cleanup.get("durationMs") or 0),
        "errorCount": int(cleanup.get("errorCount") or 0),
        "errors": [str(item)[:240] for item in (cleanup.get("errors") or [])[:3]],
    }


def _local_reference_context(
    *,
    task_id: int | None,
    local_repository_context: dict[str, Any],
    planner_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = local_repository_context.get("summary") or {}
    if str(summary.get("status") or "").upper() != "PREPARED":
        return {
            "status": "SKIPPED",
            "summary": _empty_local_reference_summary(),
            "searches": [],
            "unavailableContexts": [],
            "durationMs": 0,
        }
    try:
        worktree_path = task_head_worktree_path(task_id)
    except Exception:
        worktree_path = None
    retrieval = retrieve_local_reference_context(
        worktree_path=worktree_path,
        planner_signals=planner_signals,
    )
    if str(retrieval.get("status") or "").upper() == "UNAVAILABLE":
        unavailable_contexts = retrieval.get("unavailableContexts") or []
        reason = ""
        if unavailable_contexts and isinstance(unavailable_contexts[0], dict):
            reason = str(unavailable_contexts[0].get("reason") or "")
        summary["status"] = "UNAVAILABLE"
        summary["worktreeStatus"] = "MISSING"
        summary["failurePhase"] = "RETRIEVER_WORKTREE_VALIDATE"
        if reason:
            local_repository_context.setdefault("unavailableContexts", []).append(
                {
                    "type": "LOCAL_REPOSITORY",
                    "reason": _truncate(reason, 240),
                }
            )
    return retrieval


def _local_reference_pack_context(retrieval: dict[str, Any]) -> dict[str, Any]:
    summary = dict(retrieval.get("summary") or _empty_local_reference_summary())
    status = retrieval.get("status") or "SKIPPED"
    summary["status"] = status
    searches = retrieval.get("searches") if isinstance(retrieval.get("searches"), list) else []
    included_snippet_count = sum(int(item.get("includedSnippetCount") or 0) for item in searches if isinstance(item, dict))
    summary["includedSnippetCount"] = included_snippet_count
    summary["truncated"] = bool(summary.get("truncated", False) or any(bool(item.get("truncated")) for item in searches if isinstance(item, dict)))
    context = {
        "status": status,
        "sourceIncluded": included_snippet_count > 0,
        "summary": summary,
        "searches": searches,
    }
    if included_snippet_count > 0:
        context["note"] = (
            "Bounded local worktree reference snippets for method, DTO / field, and DB / Mapper / Entity change signals. "
            "They are auxiliary evidence only."
        )
    return context


def _prioritize_local_reference_context(local_reference_context: dict[str, Any]) -> None:
    searches = [item for item in (local_reference_context.get("searches") or []) if isinstance(item, dict)]
    searches.sort(key=_local_reference_budget_rank)
    local_reference_context["searches"] = searches


def _local_reference_budget_rank(search: dict[str, Any]) -> tuple[int, int, str]:
    high_priority = _is_high_priority_reference_search(search)
    matched_file_count = int(search.get("matchedFileCount") or 0)
    return (
        0 if high_priority else 1,
        0 if _is_primary_symbol_query(search) else 1,
        -matched_file_count,
        str(search.get("query") or ""),
    )


def _is_high_priority_reference_search(search: dict[str, Any]) -> bool:
    signal_types = {str(item or "").upper() for item in (search.get("signalTypes") or [])}
    return bool(signal_types & HIGH_MISJUDGMENT_SIGNAL_TYPES)


def _is_budget_protected_reference_search(search: dict[str, Any]) -> bool:
    return _is_high_priority_reference_search(search) and _is_primary_symbol_query(search)


def _is_primary_symbol_query(search: dict[str, Any]) -> bool:
    query = str(search.get("query") or "")
    field_names = {str(item or "") for item in (search.get("fieldNames") or [])}
    return not field_names or query in field_names


def _not_injected_evidence_from_local_reference(local_reference_context: dict[str, Any]) -> dict[str, Any]:
    summary = _empty_not_injected_evidence_summary()
    for search in [item for item in (local_reference_context.get("searches") or []) if isinstance(item, dict)]:
        candidate_count = int(search.get("candidateSnippetCount") or search.get("includedSnippetCount") or 0)
        included_count = int(search.get("includedSnippetCount") or 0)
        cut_count = max(candidate_count - included_count, 0)
        if cut_count <= 0:
            continue
        _append_not_injected_evidence_item(
            summary,
            _not_injected_local_reference_item(
                search,
                cut_snippet_count=cut_count,
                reason="LOCAL_REFERENCE_SNIPPET_BUDGET",
            ),
        )
    return summary


def _empty_not_injected_evidence_summary() -> dict[str, Any]:
    return {
        "hasNotInjectedEvidence": False,
        "items": [],
        "note": "Evidence existed but was not injected; do not treat it as absent.",
    }


def _record_not_injected_local_reference(
    context_pack: dict[str, Any],
    search: dict[str, Any],
    *,
    cut_snippet_count: int,
    reason: str,
) -> None:
    if cut_snippet_count <= 0:
        return
    summary = context_pack.get("notInjectedEvidence")
    if not isinstance(summary, dict):
        summary = _empty_not_injected_evidence_summary()
        context_pack["notInjectedEvidence"] = summary
    _append_not_injected_evidence_item(
        summary,
        _not_injected_local_reference_item(
            search,
            cut_snippet_count=cut_snippet_count,
            reason=reason,
        ),
    )
    reasons = [str(item) for item in (search.get("budgetCutReasons") or []) if str(item)]
    if reason not in reasons:
        reasons.append(reason)
    search["budgetCutReasons"] = reasons[:4]


def _append_not_injected_evidence_item(summary: dict[str, Any], item: dict[str, Any]) -> None:
    items = [entry for entry in (summary.get("items") or []) if isinstance(entry, dict)]
    merge_key = (
        item.get("signal"),
        item.get("requestedContext"),
        item.get("querySummary"),
        item.get("reason"),
    )
    for existing in items:
        existing_key = (
            existing.get("signal"),
            existing.get("requestedContext"),
            existing.get("querySummary"),
            existing.get("reason"),
        )
        if existing_key != merge_key:
            continue
        existing["cutSnippetCount"] = int(existing.get("cutSnippetCount") or 0) + int(item.get("cutSnippetCount") or 0)
        existing["matchedFileCount"] = max(
            int(existing.get("matchedFileCount") or 0),
            int(item.get("matchedFileCount") or 0),
        )
        existing["topRelativePaths"] = _merge_limited_strings(
            existing.get("topRelativePaths") or [],
            item.get("topRelativePaths") or [],
            limit=5,
        )
        summary["hasNotInjectedEvidence"] = True
        summary["items"] = items[:NOT_INJECTED_EVIDENCE_MAX_ITEMS]
        return
    items.append(item)
    summary["hasNotInjectedEvidence"] = True
    summary["items"] = items[:NOT_INJECTED_EVIDENCE_MAX_ITEMS]
    summary["truncated"] = len(items) > NOT_INJECTED_EVIDENCE_MAX_ITEMS


def _not_injected_local_reference_item(
    search: dict[str, Any],
    *,
    cut_snippet_count: int,
    reason: str,
) -> dict[str, Any]:
    signal_types = [str(item).upper()[:80] for item in (search.get("signalTypes") or [])[:4]]
    return {
        "type": "LOCAL_REFERENCE_SNIPPET",
        "signal": ", ".join(signal_types) or "-",
        "signalTypes": signal_types,
        "requestedContext": "REFERENCE_SEARCH",
        "querySummary": _truncate(str(search.get("query") or ""), 120),
        "fieldNames": [str(item)[:80] for item in (search.get("fieldNames") or [])[:6]],
        "matchedFileCount": int(search.get("matchedFileCount") or 0),
        "cutSnippetCount": max(int(cut_snippet_count), 0),
        "topRelativePaths": [
            _truncate(str(path or ""), CONTEXT_PACK_MAX_PATH_CHARS)
            for path in (search.get("topMatchedPaths") or [])[:5]
        ],
        "reasonCode": "BUDGET_CUT",
        "reason": reason,
    }


def _merge_limited_strings(first: list[Any], second: list[Any], *, limit: int) -> list[str]:
    result: list[str] = []
    for item in [*first, *second]:
        value = str(item or "")
        if value and value not in result:
            result.append(value)
        if len(result) >= limit:
            break
    return result


def _apply_local_reference_availability(
    requested_contexts: list[dict[str, Any]],
    local_reference_context: dict[str, Any],
) -> None:
    if int((local_reference_context.get("summary") or {}).get("includedSnippetCount") or 0) <= 0:
        return
    supported_signals = {
        str(item or "").upper()
        for item in ((local_reference_context.get("summary") or {}).get("supportedSignalTypes") or [])
    }
    for item in requested_contexts:
        context_type = str(item.get("type") or "").upper()
        if context_type == "REFERENCE_SEARCH":
            item["available"] = True
            item["availableSource"] = "LOCAL_REFERENCE_CONTEXT"
            continue
        if "DB_SQL_MAPPER_CHANGED" in supported_signals and context_type in {"DB_SCHEMA_CONTEXT", "RELATED_FILE"}:
            item["available"] = True
            item["availableSource"] = "LOCAL_DB_MAPPER_ENTITY_CONTEXT"


def _empty_local_reference_summary() -> dict[str, Any]:
    return {
        "queryCount": 0,
        "matchedFileCount": 0,
        "includedSnippetCount": 0,
        "truncated": False,
        "supportedSignalTypes": [],
        "skippedSignalTypes": [],
    }


def _local_reference_progress_summary(local_reference: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(local_reference.get("status") or ""),
        "queryCount": int(local_reference.get("queryCount") or 0),
        "matchedFileCount": int(local_reference.get("matchedFileCount") or 0),
        "includedSnippetCount": int(local_reference.get("includedSnippetCount") or 0),
        "truncated": bool(local_reference.get("truncated", False)),
        "supportedSignalTypes": [str(item) for item in (local_reference.get("supportedSignalTypes") or [])[:12]],
        "skippedSignalTypes": [
            {
                "type": str(item.get("type") or ""),
                "count": int(item.get("count") or 0),
            }
            for item in (local_reference.get("skippedSignalTypes") or [])[:12]
            if isinstance(item, dict)
        ],
    }


def _sync_local_reference_summary(context_pack: dict[str, Any], *, truncated: bool) -> None:
    local_reference = context_pack.get("localReferenceContext") or {}
    searches = [item for item in (local_reference.get("searches") or []) if isinstance(item, dict)]
    included_snippet_count = sum(int(item.get("includedSnippetCount") or 0) for item in searches)
    summary = local_reference.get("summary") or _empty_local_reference_summary()
    summary["status"] = local_reference.get("status") or summary.get("status") or ""
    summary["includedSnippetCount"] = included_snippet_count
    summary["truncated"] = bool(summary.get("truncated", False) or truncated)
    local_reference["summary"] = summary
    local_reference["sourceIncluded"] = included_snippet_count > 0
    context_pack["localReferenceContext"] = local_reference
    context_pack["localReferenceSearch"] = summary


def _observability_summary(
    *,
    planner_signals: list[dict[str, Any]],
    requested_contexts: list[dict[str, Any]],
    local_reference_context: dict[str, Any],
    budget_cut_summary: dict[str, Any],
) -> dict[str, Any]:
    planner_signal_type_counts = _count_items(str(item.get("type") or "").upper() for item in planner_signals)
    retriever_supported_signal_types = sorted(SUPPORTED_REFERENCE_SIGNAL_TYPES)
    retriever_unsupported_signal_type_counts = _unsupported_signal_type_counts(planner_signals)
    requested_context_availability = _requested_context_availability(requested_contexts)
    rule_gap_items = _rule_gap_items(
        planner_signals=planner_signals,
        requested_contexts=requested_contexts,
        local_reference_context=local_reference_context,
        budget_cut_summary=budget_cut_summary,
    )
    return {
        "plannerSignalTypeCounts": planner_signal_type_counts,
        "retrieverSupportedSignalTypes": retriever_supported_signal_types,
        "retrieverUnsupportedSignalTypeCounts": retriever_unsupported_signal_type_counts,
        "requestedContextAvailability": requested_context_availability,
        "budgetCutSummary": budget_cut_summary,
        "ruleGapSummary": _rule_gap_summary(rule_gap_items),
        "ruleGapItems": rule_gap_items,
    }


def _count_items(values: Any) -> list[dict[str, Any]]:
    counter = Counter(value for value in values if value)
    return [{"type": key, "count": int(value)} for key, value in sorted(counter.items())]


def _unsupported_signal_type_counts(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _count_items(
        str(signal.get("type") or "").upper()
        for signal in signals
        if str(signal.get("type") or "").upper() not in SUPPORTED_REFERENCE_SIGNAL_TYPES
    )


def _requested_context_availability(requested_contexts: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    reason_counter: Counter[str] = Counter()
    for item in requested_contexts:
        context_type = str(item.get("type") or "").upper()
        available = bool(item.get("available"))
        reason_code = None if available else _requested_context_reason_code(context_type)
        if reason_code:
            reason_counter[reason_code] += 1
        entry = {
            "type": context_type,
            "available": available,
            "signalCount": int(item.get("signalCount") or 0),
            "priority": str(item.get("priority") or "MEDIUM").upper(),
        }
        if available and item.get("availableSource"):
            entry["availableSource"] = str(item.get("availableSource") or "")[:120]
        if reason_code:
            entry["reasonCode"] = reason_code
        items.append(entry)
    return {
        "total": len(requested_contexts),
        "available": sum(1 for item in items if item.get("available")),
        "unavailable": sum(1 for item in items if not item.get("available")),
        "items": items[:CONTEXT_PLANNER_MAX_REQUESTED_CONTEXTS],
        "unavailableReasonCounts": [
            {"reasonCode": key, "count": int(value)}
            for key, value in sorted(reason_counter.items())
        ],
    }


def _requested_context_reason_code(context_type: str) -> str:
    if context_type == "REFERENCE_SEARCH":
        return "NO_REFERENCE_SNIPPETS"
    if context_type == "SAME_FILE_CONTEXT":
        return "SAME_FILE_CONTEXT_UNAVAILABLE"
    if context_type == "TEST_RESULT_CONTEXT":
        return "TESTS_NOT_EXECUTED"
    return "CAPABILITY_NOT_IMPLEMENTED"


def _budget_count_snapshot(context_pack: dict[str, Any]) -> dict[str, Any]:
    changed = context_pack.get("changedFilesSummary") or {}
    same_file = context_pack.get("sameFileContext") or {}
    local_reference = context_pack.get("localReferenceContext") or {}
    local_searches = [item for item in (local_reference.get("searches") or []) if isinstance(item, dict)]
    return {
        "includedChangedFileCount": int(changed.get("included") or 0),
        "sameFileSourceSnippetCount": int(same_file.get("sourceSnippetCount") or 0),
        "sameFileSourceFileCount": int(same_file.get("includedSourceFileCount") or 0),
        "localReferenceSnippetCount": sum(int(item.get("includedSnippetCount") or 0) for item in local_searches),
        "localReferenceSearchCount": len(local_searches),
        "hasLocalReferenceContext": bool(local_reference),
    }


def _budget_cut_summary(
    context_pack: dict[str, Any],
    before: dict[str, Any],
    *,
    prompt_length: int,
    truncated_by_budget: bool,
) -> dict[str, Any]:
    after = _budget_count_snapshot(context_pack)
    changed = context_pack.get("changedFilesSummary") or {}
    same_file = context_pack.get("sameFileContext") or {}
    local_reference = context_pack.get("localReferenceSearch") or {}
    changed_files_excluded = max(int(changed.get("total") or 0) - int(changed.get("included") or 0), 0)
    same_file_candidate_excluded = (
        max(
            int(same_file.get("candidateSourceFileCount") or 0) - int(same_file.get("includedSourceFileCount") or 0),
            0,
        )
        if int(same_file.get("includedSourceFileCount") or 0) > 0
        else 0
    )
    return {
        "truncated": bool(
            truncated_by_budget
            or changed.get("truncated")
            or local_reference.get("truncated")
            or changed_files_excluded > 0
            or same_file_candidate_excluded > 0
        ),
        "maxTotalChars": CONTEXT_PACK_MAX_TOTAL_CHARS,
        "promptLength": int(prompt_length),
        "changedFilesExcluded": changed_files_excluded,
        "changedFilesRemovedByPromptBudget": max(
            int(before.get("includedChangedFileCount") or 0) - int(after.get("includedChangedFileCount") or 0),
            0,
        ),
        "sameFileCandidateFilesExcluded": same_file_candidate_excluded,
        "sameFileSourceFilesRemoved": max(
            int(before.get("sameFileSourceFileCount") or 0) - int(after.get("sameFileSourceFileCount") or 0),
            0,
        ),
        "sameFileSourceSnippetsRemoved": max(
            int(before.get("sameFileSourceSnippetCount") or 0) - int(after.get("sameFileSourceSnippetCount") or 0),
            0,
        ),
        "localReferenceSearchesRemoved": max(
            int(before.get("localReferenceSearchCount") or 0) - int(after.get("localReferenceSearchCount") or 0),
            0,
        ),
        "localReferenceSnippetsRemoved": max(
            int(before.get("localReferenceSnippetCount") or 0) - int(after.get("localReferenceSnippetCount") or 0),
            0,
        ),
        "localReferenceContextRemoved": bool(before.get("hasLocalReferenceContext") and not after.get("hasLocalReferenceContext")),
        "localReferenceCutDetails": _local_reference_cut_details(context_pack),
        "notInjectedEvidence": (context_pack.get("notInjectedEvidence") or {}).get("items") or [],
        "protectedSignalTypes": sorted(HIGH_MISJUDGMENT_SIGNAL_TYPES),
        "localReferenceMinSnippetsPerProtectedSearch": LOCAL_REFERENCE_MIN_SNIPPETS_PER_HIGH_SIGNAL_SEARCH,
    }


def _local_reference_cut_details(context_pack: dict[str, Any]) -> list[dict[str, Any]]:
    local_reference = context_pack.get("localReferenceContext") or {}
    searches = [item for item in (local_reference.get("searches") or []) if isinstance(item, dict)]
    details: list[dict[str, Any]] = []
    for search in searches:
        candidate_count = int(search.get("candidateSnippetCount") or search.get("includedSnippetCount") or 0)
        included_count = int(search.get("includedSnippetCount") or 0)
        cut_count = max(candidate_count - included_count, 0)
        if cut_count <= 0:
            continue
        details.append(
            {
                "type": "LOCAL_REFERENCE_SNIPPET",
                "signal": ", ".join([str(item).upper()[:80] for item in (search.get("signalTypes") or [])[:4]]) or "-",
                "requestedContext": "REFERENCE_SEARCH",
                "querySummary": _truncate(str(search.get("query") or ""), 120),
                "query": _truncate(str(search.get("query") or ""), 120),
                "signalTypes": [str(item)[:80] for item in (search.get("signalTypes") or [])[:4]],
                "fieldNames": [str(item)[:80] for item in (search.get("fieldNames") or [])[:6]],
                "matchedFileCount": int(search.get("matchedFileCount") or 0),
                "candidateSnippetCount": candidate_count,
                "includedSnippetCount": included_count,
                "cutSnippetCount": cut_count,
                "topMatchedPaths": [
                    _truncate(str(path or ""), CONTEXT_PACK_MAX_PATH_CHARS)
                    for path in (search.get("topMatchedPaths") or [])[:5]
                ],
                "topRelativePaths": [
                    _truncate(str(path or ""), CONTEXT_PACK_MAX_PATH_CHARS)
                    for path in (search.get("topMatchedPaths") or [])[:5]
                ],
                "reasonCode": "BUDGET_CUT",
                "reason": _local_reference_cut_reason(search),
            }
        )
    return details[:8]


def _local_reference_cut_reason(search: dict[str, Any]) -> str:
    reasons = [str(item) for item in (search.get("budgetCutReasons") or []) if str(item)]
    if reasons:
        return ", ".join(reasons[:3])
    return "LOCAL_REFERENCE_SNIPPET_BUDGET"


def _rule_gap_items(
    *,
    planner_signals: list[dict[str, Any]],
    requested_contexts: list[dict[str, Any]],
    local_reference_context: dict[str, Any],
    budget_cut_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    by_signal: dict[str, dict[str, Any]] = {}
    for signal in planner_signals:
        signal_type = str(signal.get("type") or "").upper()
        if not signal_type or signal_type in SUPPORTED_REFERENCE_SIGNAL_TYPES:
            continue
        group = by_signal.setdefault(
            signal_type,
            {
                "count": 0,
                "priority": "LOW",
                "requested": set(),
            },
        )
        group["count"] += 1
        group["priority"] = _higher_priority(str(group.get("priority") or "LOW"), str(signal.get("priority") or "MEDIUM"))
        for context_type in signal.get("requestedContextTypes") or []:
            normalized = str(context_type or "").upper()
            if normalized:
                group["requested"].add(normalized)
    for signal_type, group in sorted(by_signal.items()):
        requested = sorted(group["requested"])
        items.append(
            _rule_gap_item(
                "UNSUPPORTED_PLANNER_SIGNAL",
                signal_type,
                ", ".join(requested[:4]) or "-",
                _suggested_capability(signal_type, requested[:1] or None),
                f"{group.get('priority')} priority signal occurred {int(group.get('count') or 0)} time(s), but Local Retriever does not support it yet.",
            )
        )

    for item in requested_contexts:
        if item.get("available"):
            continue
        context_type = str(item.get("type") or "").upper()
        items.append(
            _rule_gap_item(
                "UNAVAILABLE_REQUESTED_CONTEXT",
                _signal_for_requested_context(context_type, planner_signals),
                context_type,
                _suggested_capability(None, [context_type]),
                f"{str(item.get('priority') or 'MEDIUM').upper()} priority requested context is unavailable; signalCount={int(item.get('signalCount') or 0)}.",
            )
        )

    retrieval_status = str(local_reference_context.get("status") or "").upper()
    if retrieval_status in {"UNAVAILABLE", "PARTIAL"}:
        supported_signals = sorted(
            {
                str(signal.get("type") or "").upper()
                for signal in planner_signals
                if str(signal.get("type") or "").upper() in SUPPORTED_REFERENCE_SIGNAL_TYPES
            }
        )
        items.append(
            _rule_gap_item(
                "RETRIEVAL_FAILED",
                ", ".join(supported_signals) or "REFERENCE_SEARCH",
                "REFERENCE_SEARCH",
                "Stabilize local reference retrieval and surface retryable failure reasons.",
                f"Local Retriever status is {retrieval_status}; retrieved snippets may be incomplete.",
            )
        )

    if _has_budget_cut(budget_cut_summary):
        items.append(
            _rule_gap_item(
                "BUDGET_CUT",
                "BUDGET_CONTROLLER",
                "-",
                "Improve evidence ranking, summarization, or Context Pack budget allocation.",
                "Some candidate context was excluded or removed by Context Pack budget limits.",
            )
        )
    return items[:RULE_GAP_MAX_ITEMS]


def _rule_gap_item(
    gap_type: str,
    signal: str,
    requested_context: str,
    suggested_capability: str,
    priority_reason: str,
) -> dict[str, Any]:
    return {
        "gapType": gap_type,
        "signal": _truncate(signal, 120),
        "requestedContext": _truncate(requested_context, 160),
        "suggestedCapability": _truncate(suggested_capability, 240),
        "priorityReason": _truncate(priority_reason, 240),
    }


def _signal_for_requested_context(context_type: str, planner_signals: list[dict[str, Any]]) -> str:
    candidates = []
    for signal in planner_signals:
        if context_type in {str(item or "").upper() for item in (signal.get("requestedContextTypes") or [])}:
            signal_type = str(signal.get("type") or "").upper()
            if signal_type:
                candidates.append(signal_type)
    if not candidates:
        return "PLANNER_REQUEST"
    return ", ".join(sorted(set(candidates))[:4])


def _suggested_capability(signal_type: str | None, requested_contexts: list[str] | None) -> str:
    signal_key = str(signal_type or "").upper()
    signal_map = {
        "DTO_FIELD_CHANGED": "Add DTO / VO field reference retrieval.",
        "FIELD_DELETED": "Add field reference retrieval.",
        "DB_SQL_MAPPER_CHANGED": "Add DB / Mapper / Entity relationship retrieval.",
        "CACHE_WRITE_DELETE_CHANGED": "Add cache key and read/write usage retrieval.",
        "MQ_CONFIG_CHANGED": "Add MQ producer / consumer / topic configuration retrieval.",
        "CONFIG_FILE_CHANGED": "Add config read-point and environment override retrieval.",
        "HISTORICAL_CONTEXT_MISSING_FEEDBACK": "Convert recurring context-missing feedback into Planner / Retriever capability backlog.",
    }
    if signal_key in signal_map:
        return signal_map[signal_key]
    context_set = {str(item or "").upper() for item in (requested_contexts or [])}
    if "REFERENCE_SEARCH" in context_set or "CALLER_CONTEXT" in context_set:
        return "Add or expand local reference / caller retrieval."
    if "TEST_RESULT_CONTEXT" in context_set:
        return "Add test execution or test result context integration."
    if "RELATED_FILE" in context_set:
        return "Add bounded related-file retrieval."
    if "DB_SCHEMA_CONTEXT" in context_set:
        return "Add database schema context retrieval."
    if "CONFIG_CONTEXT" in context_set:
        return "Add runtime config context retrieval."
    if "MQ_CONFIG_CONTEXT" in context_set:
        return "Add MQ config context retrieval."
    if "CACHE_USAGE_CONTEXT" in context_set:
        return "Add cache usage context retrieval."
    return "Evaluate whether this requested context needs a dedicated Retriever capability."


def _has_budget_cut(summary: dict[str, Any]) -> bool:
    if not summary.get("truncated"):
        return False
    count_fields = [
        "changedFilesExcluded",
        "changedFilesRemovedByPromptBudget",
        "sameFileCandidateFilesExcluded",
        "sameFileSourceFilesRemoved",
        "sameFileSourceSnippetsRemoved",
        "localReferenceSearchesRemoved",
        "localReferenceSnippetsRemoved",
    ]
    return bool(summary.get("localReferenceContextRemoved") or any(int(summary.get(field) or 0) > 0 for field in count_fields))


def _rule_gap_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    gap_type_counter = Counter(str(item.get("gapType") or "") for item in items if item.get("gapType"))
    signal_counter = Counter(str(item.get("signal") or "") for item in items if item.get("signal"))
    return {
        "total": len(items),
        "byGapType": [
            {"gapType": key, "count": int(value)}
            for key, value in sorted(gap_type_counter.items())
        ],
        "topSignals": [
            {"signal": key, "count": int(value)}
            for key, value in signal_counter.most_common(5)
        ],
        "truncated": len(items) >= RULE_GAP_MAX_ITEMS,
    }


def _diff_stats(diff: str) -> tuple[int, int, int, int]:
    additions = 0
    deletions = 0
    hunk_count = 0
    context_count = 0
    for line in diff.splitlines():
        if line.startswith("@@"):
            hunk_count += 1
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
        elif line.startswith(" ") and line.strip():
            context_count += 1
    return additions, deletions, hunk_count, context_count


def _split_diff_by_path(diff_text: str) -> dict[str, str]:
    if not diff_text.strip():
        return {}
    result: dict[str, list[str]] = {}
    current_path: str | None = None
    current_lines: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current_path and current_lines:
                result[current_path] = current_lines[:]
            current_path = _path_from_diff_header(line)
            current_lines = [line]
            continue
        if current_path:
            current_lines.append(line)
    if current_path and current_lines:
        result[current_path] = current_lines
    return {path: "\n".join(lines) for path, lines in result.items() if path}


def _path_from_diff_header(line: str) -> str | None:
    parts = line.split()
    if len(parts) < 4:
        return None
    candidate = parts[3]
    if candidate.startswith("b/"):
        candidate = candidate[2:]
    if candidate == "/dev/null" and parts[2].startswith("a/"):
        candidate = parts[2][2:]
    return _normalize_path(candidate)


def _change_type(item: dict[str, Any]) -> str:
    raw = str(item.get("changeType") or "").strip().upper()
    if raw:
        return raw
    if bool(item.get("newFile")):
        return "ADDED"
    if bool(item.get("deletedFile")):
        return "DELETED"
    if bool(item.get("renamedFile")):
        return "RENAMED"
    return "MODIFIED"


def _clean_path(value: Any) -> str | None:
    normalized = _normalize_path(value)
    return normalized or None


def _normalize_path(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip().lstrip("/")
    if text.startswith("a/") or text.startswith("b/"):
        text = text[2:]
    return text


def _language_for_path(file_path: str) -> str:
    suffix = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    return {
        "java": "java",
        "py": "python",
        "js": "javascript",
        "jsx": "jsx",
        "ts": "typescript",
        "tsx": "tsx",
        "sql": "sql",
        "xml": "xml",
        "json": "json",
        "yml": "yaml",
        "yaml": "yaml",
        "css": "css",
        "scss": "css",
        "sh": "shell",
        "bash": "shell",
        "md": "markdown",
    }.get(suffix, "text")


def _truncate(value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."
