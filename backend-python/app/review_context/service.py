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
from app.project_integration import gitlab_client
from app.review_feedback.models import ReviewItemFeedback
from app.review_feedback.repository import ensure_feedback_schema
from app.review_context.local_repo import prepare_local_repository_context, task_head_worktree_path
from app.review_context.local_retriever import retrieve_local_reference_context


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
        "localReferenceSearch": local_reference_context.get("summary") or _empty_local_reference_summary(),
        "contextPlan": context_plan,
        "plannerSignals": planner_signals,
        "requestedContexts": requested_contexts,
        "contextMissingFeedbackSummary": feedback_summary,
        "unavailableContexts": unavailable_contexts,
        "unavailableContextsTruncated": len(unavailable_contexts) >= CONTEXT_PACK_MAX_UNAVAILABLE_CONTEXTS,
    }
    review_context = {
        "version": CONTEXT_PACK_VERSION,
        "mode": mode or "DIFF_TEXT",
        "contextPack": context_pack,
    }
    prompt_text, truncated_by_budget = _fit_context_pack_budget(context_pack, review_context)

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
        "localReferenceQueryCount": context_pack["localReferenceSearch"].get("queryCount", 0),
        "localReferenceMatchedFileCount": context_pack["localReferenceSearch"].get("matchedFileCount", 0),
        "localReferenceSnippetCount": context_pack["localReferenceSearch"].get("includedSnippetCount", 0),
        "localReferenceTruncated": bool(context_pack["localReferenceSearch"].get("truncated", False)),
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
        "REFERENCE_SEARCH": "Reference snippets are not injected until V2-F-7.",
        "CALLER_CONTEXT": "Caller snippets are not injected until V2-F-7.",
        "CALLEE_CONTEXT": "Callee inspection is not performed.",
        "SAME_CLASS_METHODS": "Class parsing is not performed.",
        "RELATED_FILE": "Related files are not read.",
        "DB_SCHEMA_CONTEXT": "DB schema is not retrieved.",
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
            "reason": "Reference, caller, and usage search is not performed.",
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
            "reason": "Related files and full project scan are not performed.",
        },
        {
            "type": "DB_SCHEMA_CONTEXT",
            "reason": "Database schema is not retrieved.",
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
        break
    return prompt_text, truncated_by_budget


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
        "contextMissingFeedbackTotal": feedback["total"],
        "topMissingContextTypes": feedback["byMissingContextType"][:3],
        "plannerSignalCount": context_plan.get("plannerSignalCount", 0),
        "plannerSignalTotal": context_plan.get("plannerSignalTotal", 0),
        "requestedContextCount": context_plan.get("requestedContextCount", 0),
        "requestedContextTypeCounts": context_plan.get("requestedContextTypeCounts", [])[:8],
        "plannerUnavailableContextCount": context_plan.get("unavailableContextCount", 0),
        "unavailableContextCount": meta["unavailableContextCount"],
        "promptLength": meta["promptLength"],
        "truncated": meta["truncated"],
    }


def _local_repository_progress_summary(local_repository: dict[str, Any]) -> dict[str, Any]:
    return {
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
    return retrieve_local_reference_context(
        worktree_path=worktree_path,
        planner_signals=planner_signals,
    )


def _empty_local_reference_summary() -> dict[str, Any]:
    return {
        "queryCount": 0,
        "matchedFileCount": 0,
        "includedSnippetCount": 0,
        "truncated": False,
    }


def _local_reference_progress_summary(local_reference: dict[str, Any]) -> dict[str, Any]:
    return {
        "queryCount": int(local_reference.get("queryCount") or 0),
        "matchedFileCount": int(local_reference.get("matchedFileCount") or 0),
        "includedSnippetCount": int(local_reference.get("includedSnippetCount") or 0),
        "truncated": bool(local_reference.get("truncated", False)),
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
