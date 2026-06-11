from __future__ import annotations

from collections import Counter
import json
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.json_utils import read_json_array
from app.project_integration import gitlab_client
from app.review_feedback.models import ReviewItemFeedback
from app.review_feedback.repository import ensure_feedback_schema


CONTEXT_PACK_VERSION = "context-pack-v0"
CONTEXT_PACK_MAX_TOTAL_CHARS = 6000
CONTEXT_PACK_MAX_CHANGED_FILES = 30
CONTEXT_PACK_MAX_FEEDBACK_BUCKETS = 8
CONTEXT_PACK_MAX_UNAVAILABLE_CONTEXTS = 12
CONTEXT_PACK_MAX_PATH_CHARS = 240
CONTEXT_PACK_MAX_SOURCE_CONTEXT_FILES = 5
CONTEXT_PACK_MAX_SNIPPETS_PER_FILE = 3
CONTEXT_PACK_SOURCE_CONTEXT_WINDOW_LINES = 30
CONTEXT_PACK_MAX_SNIPPET_CHARS = 3500


def build_review_context_pack(
    db: Session | None,
    *,
    project_id: int | None,
    changed_files: list[Any] | None,
    diff_text: str | None,
    mode: str | None,
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
    unavailable_contexts = _unavailable_contexts(files, source_unavailable_contexts)
    context_pack = {
        "version": CONTEXT_PACK_VERSION,
        "changedFilesSummary": _changed_files_summary(files, diff_text),
        "sameFileContext": same_file_context,
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
    }
    return {
        "reviewContext": review_context,
        "contextPack": context_pack,
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


def _unavailable_contexts(
    files: list[dict[str, Any]],
    source_unavailable_contexts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contexts = [
        {
            "type": "SAME_FILE_FULL_SOURCE",
            "reason": "V2-F-2 includes bounded snippets only; full file source is never included.",
        },
        {
            "type": "REFERENCE_SEARCH",
            "reason": "V2-F-1 does not search references, callers, or usages.",
        },
        {
            "type": "CALLER_CONTEXT",
            "reason": "V2-F-1 does not inspect callers outside the changed diff.",
        },
        {
            "type": "CALLEE_CONTEXT",
            "reason": "V2-F-1 does not inspect callees outside the changed diff.",
        },
        {
            "type": "RELATED_FILE",
            "reason": "V2-F-1 does not scan related files or the full project.",
        },
        {
            "type": "DB_SCHEMA_CONTEXT",
            "reason": "V2-F-1 does not retrieve database schema beyond the submitted diff.",
        },
        {
            "type": "CONFIG_CONTEXT",
            "reason": "V2-F-1 does not retrieve runtime configuration beyond the submitted diff.",
        },
        {
            "type": "TEST_RESULT_CONTEXT",
            "reason": "V2-F-1 does not execute tests or include test results.",
        },
    ]
    if any(not str(file.get("diffText") or "").strip() for file in files):
        contexts.insert(
            1,
            {
                "type": "DIFF_TEXT_FOR_SOME_FILES",
                "reason": "Some changed files have no diff text, so only file path metadata is available.",
            },
        )
    return [*source_unavailable_contexts, *contexts][:CONTEXT_PACK_MAX_UNAVAILABLE_CONTEXTS]


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
    feedback = context_pack["contextMissingFeedbackSummary"]
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
        "contextMissingFeedbackTotal": feedback["total"],
        "topMissingContextTypes": feedback["byMissingContextType"][:3],
        "unavailableContextCount": meta["unavailableContextCount"],
        "promptLength": meta["promptLength"],
        "truncated": meta["truncated"],
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
