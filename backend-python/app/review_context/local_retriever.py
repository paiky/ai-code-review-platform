from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from time import perf_counter
from typing import Any

from app.core.config import get_settings


SUPPORTED_REFERENCE_SIGNAL_TYPES = {"METHOD_DELETED", "METHOD_SIGNATURE_CHANGED"}
LOCAL_REFERENCE_CONTEXT_TYPE = "REFERENCE_SEARCH"

_DEFAULT_MAX_QUERIES = 8
_DEFAULT_MAX_MATCHED_FILES_PER_QUERY = 10
_DEFAULT_MAX_SNIPPETS_PER_QUERY = 6
_DEFAULT_SNIPPET_CONTEXT_LINES = 30
_DEFAULT_MAX_SNIPPET_CHARS = 3000
_DEFAULT_MAX_TOTAL_CHARS = 12000
_DEFAULT_MAX_SEARCH_SECONDS = 30
_DEFAULT_RG_MAX_MATCHES_PER_FILE = 20

_IGNORED_DIR_NAMES = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "target",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".codegraph",
}
_RG_EXCLUDE_GLOBS = (
    "!**/.git/**",
    "!**/node_modules/**",
    "!**/dist/**",
    "!**/build/**",
    "!**/target/**",
    "!**/.venv/**",
    "!**/__pycache__/**",
    "!**/.pytest_cache/**",
    "!**/.codegraph/**",
)


class LocalReferenceSearchError(Exception):
    pass


def retrieve_local_reference_context(
    *,
    worktree_path: Path | str | None,
    planner_signals: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    queries = _queries_from_signals(planner_signals or [])
    max_queries = _env_int("LOCAL_CONTEXT_MAX_QUERIES", _DEFAULT_MAX_QUERIES, minimum=1)
    selected_queries = queries[:max_queries]
    truncated = len(queries) > len(selected_queries)
    if not selected_queries:
        return _result("SKIPPED", query_count=0, matched_files=set(), searches=[], truncated=truncated)

    started = perf_counter()
    try:
        worktree = _validate_worktree_path(worktree_path)
    except LocalReferenceSearchError as exception:
        return _result(
            "UNAVAILABLE",
            query_count=0,
            matched_files=set(),
            searches=[],
            truncated=truncated,
            unavailable_contexts=[
                {
                    "type": LOCAL_REFERENCE_CONTEXT_TYPE,
                    "reason": str(exception),
                }
            ],
            duration_ms=_duration_ms(started),
        )

    searches: list[dict[str, Any]] = []
    matched_files: set[str] = set()
    unavailable_contexts: list[dict[str, Any]] = []
    for query in selected_queries:
        try:
            search, search_matched_files = _search_query(worktree, query)
        except LocalReferenceSearchError as exception:
            truncated = True
            unavailable_contexts.append(
                {
                    "type": LOCAL_REFERENCE_CONTEXT_TYPE,
                    "reason": str(exception),
                }
            )
            continue
        searches.append(search)
        matched_files.update(search_matched_files)
        truncated = truncated or bool(search.get("truncated"))

    if _enforce_total_budget(searches):
        truncated = True
    status = "RETRIEVED"
    if unavailable_contexts and searches:
        status = "PARTIAL"
    elif unavailable_contexts:
        status = "UNAVAILABLE"
    return _result(
        status,
        query_count=len(selected_queries),
        matched_files=matched_files,
        searches=searches,
        truncated=truncated,
        unavailable_contexts=unavailable_contexts,
        duration_ms=_duration_ms(started),
    )


def _queries_from_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queries: dict[str, dict[str, Any]] = {}
    for signal in signals:
        signal_type = str(signal.get("type") or "").strip().upper()
        if signal_type not in SUPPORTED_REFERENCE_SIGNAL_TYPES:
            continue
        details = signal.get("details") if isinstance(signal.get("details"), dict) else {}
        method_names = details.get("methodNames") if isinstance(details, dict) else []
        if not isinstance(method_names, list):
            continue
        for method_name in method_names:
            query = str(method_name or "").strip()
            if not query:
                continue
            item = queries.setdefault(
                query,
                {
                    "query": query,
                    "signalTypes": set(),
                    "filePaths": set(),
                },
            )
            item["signalTypes"].add(signal_type)
            file_path = str(signal.get("filePath") or "").strip()
            if file_path:
                item["filePaths"].add(file_path)
    result = []
    for item in queries.values():
        result.append(
            {
                "query": item["query"],
                "signalTypes": sorted(item["signalTypes"]),
                "filePaths": sorted(item["filePaths"]),
            }
        )
    return result


def _search_query(worktree: Path, query: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    output = _run_rg(worktree, str(query["query"]))
    matches = _parse_rg_matches(output, worktree)
    matched_paths = set(matches)
    max_files = _env_int(
        "LOCAL_CONTEXT_MAX_MATCHED_FILES_PER_QUERY",
        _DEFAULT_MAX_MATCHED_FILES_PER_QUERY,
        minimum=1,
    )
    max_snippets = _env_int(
        "LOCAL_CONTEXT_MAX_SNIPPETS_PER_QUERY",
        _DEFAULT_MAX_SNIPPETS_PER_QUERY,
        minimum=1,
    )
    snippets: list[dict[str, Any]] = []
    ranked_paths = _rank_paths(matches, query)
    candidate_snippet_count = 0
    for relative_path in ranked_paths[:max_files]:
        candidate_snippet_count += len(_line_windows(matches[relative_path], _line_count(worktree, relative_path)))
        if len(snippets) >= max_snippets:
            break
        snippets.extend(
            _snippets_for_file(
                worktree,
                relative_path,
                matches[relative_path],
                max_snippets=max_snippets - len(snippets),
            )
        )
    truncated = len(matches) > max_files or candidate_snippet_count > len(snippets)
    search = {
        "type": "REFERENCE_SEARCH",
        "query": str(query["query"]),
        "signalTypes": query.get("signalTypes") or [],
        "filePaths": query.get("filePaths") or [],
        "matchedFileCount": len(matched_paths),
        "includedSnippetCount": len(snippets),
        "truncated": bool(truncated),
        "snippets": snippets,
    }
    return search, matched_paths


def _run_rg(worktree: Path, query: str) -> str:
    args = _rg_args(query)
    try:
        completed = subprocess.run(
            args,
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=_env_int("LOCAL_REPO_MAX_SEARCH_SECONDS", _DEFAULT_MAX_SEARCH_SECONDS, minimum=1),
            check=False,
        )
    except subprocess.TimeoutExpired as exception:
        raise LocalReferenceSearchError("Local reference search timed out.") from exception
    except OSError as exception:
        raise LocalReferenceSearchError(f"Local reference search cannot start: {_public_error(str(exception), worktree)}") from exception
    if completed.returncode == 1:
        return ""
    if completed.returncode != 0:
        output = completed.stderr or completed.stdout or ""
        raise LocalReferenceSearchError(f"Local reference search failed: {_public_error(output, worktree)}")
    return completed.stdout or ""


def _rg_args(query: str) -> list[str]:
    args = [
        "rg",
        "--json",
        "--fixed-strings",
        "--line-number",
        "--column",
        "--color",
        "never",
        "--no-messages",
        "--max-count",
        str(_env_int("LOCAL_CONTEXT_RG_MAX_MATCHES_PER_FILE", _DEFAULT_RG_MAX_MATCHES_PER_FILE, minimum=1)),
    ]
    for glob in _RG_EXCLUDE_GLOBS:
        args.extend(["--glob", glob])
    args.extend(["-e", query, "."])
    return args


def _parse_rg_matches(output: str, worktree: Path) -> dict[str, list[int]]:
    matches: dict[str, list[int]] = {}
    for raw_line in output.splitlines():
        try:
            item = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if item.get("type") != "match":
            continue
        data = item.get("data") or {}
        relative_path = _relative_path_from_rg(data.get("path") or {}, worktree)
        line_number = data.get("line_number")
        if not relative_path or _is_ignored_relative_path(relative_path):
            continue
        try:
            number = max(int(line_number), 1)
        except (TypeError, ValueError):
            continue
        matches.setdefault(relative_path, []).append(number)
    return {path: sorted(set(lines)) for path, lines in matches.items()}


def _relative_path_from_rg(path_item: dict[str, Any], worktree: Path) -> str | None:
    raw_path = str(path_item.get("text") or "").replace("\\", "/").strip()
    if not raw_path:
        return None
    if raw_path.startswith("./"):
        raw_path = raw_path[2:]
    candidate = Path(raw_path)
    if candidate.is_absolute():
        try:
            raw_path = str(candidate.resolve(strict=False).relative_to(worktree)).replace("\\", "/")
        except ValueError:
            return None
    if raw_path.startswith("../") or "/../" in raw_path or raw_path == "..":
        return None
    return raw_path.strip("/")


def _rank_paths(matches: dict[str, list[int]], query: dict[str, Any]) -> list[str]:
    changed_paths = {str(path).replace("\\", "/").strip("/") for path in query.get("filePaths") or []}
    return sorted(matches, key=lambda path: (_path_rank(path, changed_paths), path))


def _path_rank(path: str, changed_paths: set[str]) -> int:
    lower = path.lower()
    rank = 50
    if lower in {item.lower() for item in changed_paths}:
        rank -= 10
    if lower.startswith("src/main/") or "/src/main/" in lower:
        rank -= 30
    elif lower.startswith("src/"):
        rank -= 15
    if any(token in lower for token in ("controller", "service", "mapper", "repository", "handler")):
        rank -= 10
    if "/test/" in lower or lower.startswith("test/") or lower.startswith("tests/") or "src/test/" in lower:
        rank += 35
    if any(token in lower for token in ("generated", "snapshot", "fixture", "fixtures")):
        rank += 40
    if lower.endswith((".md", ".lock", ".log", ".min.js", ".map")):
        rank += 60
    return rank


def _snippets_for_file(
    worktree: Path,
    relative_path: str,
    match_lines: list[int],
    *,
    max_snippets: int,
) -> list[dict[str, Any]]:
    try:
        file_path = _safe_file_path(worktree, relative_path)
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, UnicodeError, LocalReferenceSearchError):
        return []
    if not lines:
        return []
    snippets: list[dict[str, Any]] = []
    for start, end, match_line in _line_windows(match_lines, len(lines))[:max_snippets]:
        snippet_lines = [{"number": number, "text": lines[number - 1]} for number in range(start, end + 1)]
        snippet = {
            "path": relative_path,
            "startLine": start,
            "endLine": end,
            "matchLine": match_line,
            "reason": "METHOD_REFERENCE",
            "truncated": False,
            "lines": snippet_lines,
        }
        _truncate_snippet(snippet)
        snippets.append(snippet)
    return snippets


def _line_count(worktree: Path, relative_path: str) -> int:
    try:
        file_path = _safe_file_path(worktree, relative_path)
        return len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
    except (OSError, UnicodeError, LocalReferenceSearchError):
        return 0


def _line_windows(match_lines: list[int], total_lines: int) -> list[tuple[int, int, int]]:
    context_lines = _env_int("LOCAL_CONTEXT_SNIPPET_CONTEXT_LINES", _DEFAULT_SNIPPET_CONTEXT_LINES, minimum=0)
    windows: list[tuple[int, int, int]] = []
    for match_line in sorted(set(match_lines)):
        line = min(max(match_line, 1), total_lines)
        start = max(line - context_lines, 1)
        end = min(line + context_lines, total_lines)
        if windows and start <= windows[-1][1] + 1:
            previous_start, previous_end, previous_match = windows[-1]
            windows[-1] = (previous_start, max(previous_end, end), previous_match)
            continue
        windows.append((start, end, line))
    return windows


def _truncate_snippet(snippet: dict[str, Any]) -> None:
    limit = _env_int("LOCAL_CONTEXT_MAX_SNIPPET_CHARS", _DEFAULT_MAX_SNIPPET_CHARS, minimum=200)
    while len(json.dumps(snippet, ensure_ascii=False, separators=(",", ":"))) > limit:
        lines = snippet.get("lines") or []
        if len(lines) > 1:
            lines.pop()
            snippet["lines"] = lines
            snippet["endLine"] = lines[-1]["number"]
            snippet["truncated"] = True
            continue
        if lines and len(str(lines[0].get("text") or "")) > 80:
            lines[0]["text"] = str(lines[0].get("text") or "")[:77].rstrip() + "..."
            snippet["lines"] = lines
            snippet["truncated"] = True
        break


def _enforce_total_budget(searches: list[dict[str, Any]]) -> bool:
    limit = _env_int("LOCAL_CONTEXT_MAX_TOTAL_CHARS", _DEFAULT_MAX_TOTAL_CHARS, minimum=1000)
    truncated = False
    while len(json.dumps(searches, ensure_ascii=False, separators=(",", ":"))) > limit:
        target = next((item for item in reversed(searches) if item.get("snippets")), None)
        if target is None:
            break
        target["snippets"].pop()
        target["includedSnippetCount"] = len(target.get("snippets") or [])
        target["truncated"] = True
        truncated = True
    return truncated


def _validate_worktree_path(worktree_path: Path | str | None) -> Path:
    if worktree_path is None:
        raise LocalReferenceSearchError("Task head worktree is unavailable; local reference search is skipped.")
    settings = get_settings()
    root = Path(settings.local_repo_workspace_root or ".local/review-workspaces").expanduser().resolve(strict=False)
    candidate = Path(worktree_path).expanduser().resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exception:
        raise LocalReferenceSearchError("Task head worktree escapes LOCAL_REPO_WORKSPACE_ROOT.") from exception
    if not candidate.is_dir():
        raise LocalReferenceSearchError("Task head worktree is unavailable; local reference search is skipped.")
    return candidate


def _safe_file_path(worktree: Path, relative_path: str) -> Path:
    candidate = worktree.joinpath(relative_path).resolve(strict=False)
    try:
        candidate.relative_to(worktree)
    except ValueError as exception:
        raise LocalReferenceSearchError("Matched file escapes task head worktree.") from exception
    return candidate


def _is_ignored_relative_path(relative_path: str) -> bool:
    parts = [part.lower() for part in relative_path.replace("\\", "/").split("/") if part]
    return any(part in _IGNORED_DIR_NAMES for part in parts)


def _result(
    status: str,
    *,
    query_count: int,
    matched_files: set[str],
    searches: list[dict[str, Any]],
    truncated: bool,
    unavailable_contexts: list[dict[str, Any]] | None = None,
    duration_ms: int = 0,
) -> dict[str, Any]:
    included_snippet_count = sum(int(item.get("includedSnippetCount") or 0) for item in searches)
    return {
        "status": status,
        "summary": {
            "queryCount": int(query_count),
            "matchedFileCount": len(matched_files),
            "includedSnippetCount": included_snippet_count,
            "truncated": bool(truncated),
        },
        "searches": searches,
        "unavailableContexts": unavailable_contexts or [],
        "durationMs": int(duration_ms),
    }


def _env_int(name: str, default: int, *, minimum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(value, minimum)


def _duration_ms(started: float) -> int:
    return max(int((perf_counter() - started) * 1000), 0)


def _public_error(value: str, worktree: Path) -> str:
    text = str(value or "").replace(str(worktree), "<task-worktree>")
    root = str(Path(get_settings().local_repo_workspace_root or ".local/review-workspaces").expanduser().resolve(strict=False))
    text = text.replace(root, "<workspace-root>")
    return text.strip()[:500] or "unknown error"
