from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
from time import monotonic, perf_counter
from typing import Any, Iterable

from app.agent_review_spike.schema import normalize_relative_path


DENIED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".cursor",
    ".claude",
    ".codex",
    ".local",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".codegraph",
}
DENIED_FILE_NAMES = {
    "id_rsa",
    "id_ed25519",
    "credentials",
    "credentials.json",
    "secrets.json",
    "secrets.yml",
    "secrets.yaml",
    "application-prod.yml",
    "application-prod.yaml",
    "application-prod.properties",
}
DENIED_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
    ".jks",
    ".keystore",
}


class ReviewToolError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class ToolBudget:
    max_calls: int = 40
    max_source_bytes: int = 200_000
    calls: int = 0
    source_bytes: int = 0
    diff_bytes: int = 0
    blocked_access_count: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    top_path_summaries: list[dict[str, Any]] = field(default_factory=list)

    def begin(self, tool: str) -> float:
        if self.calls >= self.max_calls:
            raise ReviewToolError("TOOL_CALL_BUDGET_EXCEEDED", "tool call budget exhausted")
        self.calls += 1
        return perf_counter()

    def finish(
        self,
        tool: str,
        started: float,
        *,
        source_bytes: int = 0,
        item_count: int = 0,
        paths: Iterable[str] = (),
        status: str = "SUCCESS",
        error_code: str | None = None,
        query: str | None = None,
    ) -> None:
        if source_bytes > 0 and self.source_bytes + source_bytes > self.max_source_bytes:
            raise ReviewToolError("SOURCE_BUDGET_EXCEEDED", "source byte budget exhausted")
        self.source_bytes += max(source_bytes, 0)
        if tool == "read_diff_range":
            self.diff_bytes += max(source_bytes, 0)
        safe_paths = []
        for path in paths:
            normalized = str(path or "").replace("\\", "/")[:300]
            if normalized:
                summary = _path_summary(normalized)
                if summary not in self.top_path_summaries:
                    self.top_path_summaries.append(summary)
                safe_paths.append(summary)
        event = {
            "tool": tool,
            "status": status,
            "durationMs": max(int((perf_counter() - started) * 1000), 0),
            "itemCount": max(int(item_count), 0),
            "sourceBytes": max(int(source_bytes), 0),
            "pathSummary": safe_paths[:5],
        }
        if error_code:
            event["errorCode"] = error_code[:80]
        if query is not None:
            event["queryHash"] = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
        self.events.append(event)

    def blocked(self) -> None:
        self.blocked_access_count += 1

    def summary(self) -> dict[str, Any]:
        return {
            "toolCallCount": self.calls,
            "sourceBytesReturned": self.source_bytes,
            "diffBytesReturned": self.diff_bytes,
            "maxToolCalls": self.max_calls,
            "maxSourceBytes": self.max_source_bytes,
            "blockedAccessCount": self.blocked_access_count,
            "topPathSummaries": self.top_path_summaries[:20],
            "events": list(self.events),
        }


class ReviewWorkspace:
    def __init__(self, root: Path, *, max_file_bytes: int = 1_048_576) -> None:
        resolved = root.resolve(strict=True)
        if not resolved.is_dir():
            raise ReviewToolError("WORKTREE_NOT_FOUND", "worktree root is not a directory")
        self.root = resolved
        self.max_file_bytes = max(int(max_file_bytes), 1)

    def list_files(self, pattern: str = "**/*", limit: int = 200) -> dict[str, Any]:
        normalized_pattern = _validate_glob(pattern)
        limit = _bounded_int(limit, 1, 500, "limit")
        files = []
        truncated = False
        for path, relative in self._iter_files():
            if not _glob_matches(relative, normalized_pattern):
                continue
            if len(files) >= limit:
                truncated = True
                break
            files.append({"path": relative, "sizeBytes": path.stat().st_size})
        return {"files": files, "count": len(files), "truncated": truncated}

    def read_file_range(self, path: str, start_line: int, end_line: int) -> dict[str, Any]:
        safe_path, relative = self._resolve_file(path)
        start = _bounded_int(start_line, 1, 10_000_000, "startLine")
        end = _bounded_int(end_line, start, start + 399, "endLine")
        lines = _read_text_lines(safe_path, self.max_file_bytes)
        selected = lines[start - 1 : end]
        content = "\n".join(f"{start + index}: {line}" for index, line in enumerate(selected))
        return {
            "path": relative,
            "startLine": start,
            "endLine": start + len(selected) - 1 if selected else start,
            "lineCount": len(selected),
            "content": content,
        }

    def search_code(
        self,
        query: str,
        *,
        globs: list[str] | None = None,
        is_regex: bool = False,
        case_sensitive: bool = True,
        limit: int = 50,
        timeout_seconds: int = 10,
    ) -> dict[str, Any]:
        query_text = str(query or "")
        if not query_text or len(query_text) > 256:
            raise ReviewToolError("INVALID_QUERY", "query must contain 1 to 256 characters")
        patterns = [_validate_glob(item) for item in (globs or ["**/*"])]
        if len(patterns) > 8:
            raise ReviewToolError("INVALID_GLOB", "at most 8 globs are allowed")
        limit = _bounded_int(limit, 1, 100, "limit")
        timeout_seconds = _bounded_int(timeout_seconds, 1, 30, "timeoutSeconds")
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = None
        if is_regex:
            _validate_safe_regex(query_text)
            try:
                regex = re.compile(query_text, flags)
            except re.error as exception:
                raise ReviewToolError("INVALID_REGEX", "query is not a valid regular expression") from exception
        literal = query_text if case_sensitive else query_text.casefold()

        started = monotonic()
        matches: list[dict[str, Any]] = []
        scanned_files = 0
        timed_out = False
        for path, relative in self._iter_files():
            if not any(_glob_matches(relative, pattern) for pattern in patterns):
                continue
            if monotonic() - started > timeout_seconds:
                timed_out = True
                break
            try:
                lines = _read_text_lines(path, self.max_file_bytes)
            except ReviewToolError as exception:
                if exception.code in {"FILE_TOO_LARGE", "BINARY_FILE"}:
                    continue
                raise
            scanned_files += 1
            for line_number, line in enumerate(lines, 1):
                if monotonic() - started > timeout_seconds:
                    timed_out = True
                    break
                searchable_line = line[:20_000]
                matched = bool(regex.search(searchable_line)) if regex else literal in (
                    searchable_line if case_sensitive else searchable_line.casefold()
                )
                if not matched:
                    continue
                matches.append(
                    {
                        "path": relative,
                        "line": line_number,
                        "text": searchable_line[:500],
                    }
                )
                if len(matches) >= limit:
                    return {
                        "matches": matches,
                        "count": len(matches),
                        "scannedFileCount": scanned_files,
                        "truncated": True,
                        "timedOut": False,
                    }
            if timed_out:
                break
        return {
            "matches": matches,
            "count": len(matches),
            "scannedFileCount": scanned_files,
            "truncated": False,
            "timedOut": timed_out,
        }

    def _resolve_file(self, value: str) -> tuple[Path, str]:
        try:
            relative = normalize_relative_path(value)
        except ValueError as exception:
            raise ReviewToolError("PATH_OUTSIDE_WORKTREE", str(exception)) from exception
        if _is_denied(relative):
            raise ReviewToolError("SENSITIVE_PATH_DENIED", "path is denied by the review policy")
        current = self.root
        for part in PurePosixPath(relative).parts:
            current = current / part
            if current.is_symlink():
                raise ReviewToolError("SYMLINK_DENIED", "symbolic links are not readable")
        try:
            resolved = current.resolve(strict=True)
            resolved.relative_to(self.root)
        except (FileNotFoundError, ValueError) as exception:
            raise ReviewToolError("PATH_OUTSIDE_WORKTREE", "path is unavailable or outside worktree") from exception
        if not resolved.is_file():
            raise ReviewToolError("FILE_NOT_FOUND", "path is not a readable file")
        if resolved.stat().st_size > self.max_file_bytes:
            raise ReviewToolError("FILE_TOO_LARGE", "file exceeds the maximum readable size")
        return resolved, relative

    def _iter_files(self) -> Iterable[tuple[Path, str]]:
        for current_root, directories, files in os.walk(self.root, followlinks=False):
            current_path = Path(current_root)
            directories[:] = sorted(
                directory
                for directory in directories
                if not (current_path / directory).is_symlink()
                and directory.casefold() not in DENIED_DIRECTORIES
            )
            for file_name in sorted(files):
                path = current_path / file_name
                if path.is_symlink():
                    continue
                relative = path.relative_to(self.root).as_posix()
                if _is_denied(relative):
                    continue
                try:
                    if path.stat().st_size > self.max_file_bytes:
                        continue
                except OSError:
                    continue
                yield path, relative


def _is_denied(relative: str) -> bool:
    parts = [part.casefold() for part in PurePosixPath(relative).parts]
    if any(part in DENIED_DIRECTORIES for part in parts[:-1]):
        return True
    name = parts[-1] if parts else ""
    if name == ".env" or name.startswith(".env."):
        return True
    if name in DENIED_FILE_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in DENIED_SUFFIXES)


def validate_review_path(value: Any) -> str:
    """Normalize a changed-file path and reject paths the Agent may never receive."""
    try:
        relative = normalize_relative_path(value)
    except ValueError as exception:
        raise ReviewToolError("PATH_OUTSIDE_WORKTREE", str(exception)) from exception
    if _is_denied(relative):
        raise ReviewToolError("SENSITIVE_PATH_DENIED", "path is denied by the review policy")
    return relative


def _validate_glob(value: Any) -> str:
    text = str(value or "**/*").strip().replace("\\", "/")
    if len(text) > 200 or text.startswith("/") or ".." in PurePosixPath(text).parts:
        raise ReviewToolError("INVALID_GLOB", "glob must be a safe relative pattern")
    return text or "**/*"


def _glob_matches(relative: str, pattern: str) -> bool:
    if fnmatchcase(relative, pattern):
        return True
    return pattern.startswith("**/") and fnmatchcase(relative, pattern[3:])


def _bounded_int(value: Any, minimum: int, maximum: int, field: str) -> int:
    if isinstance(value, bool):
        raise ReviewToolError("INVALID_ARGUMENT", f"{field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exception:
        raise ReviewToolError("INVALID_ARGUMENT", f"{field} must be an integer") from exception
    if number < minimum or number > maximum:
        raise ReviewToolError(
            "INVALID_ARGUMENT", f"{field} must be between {minimum} and {maximum}"
        )
    return number


def _validate_safe_regex(value: str) -> None:
    if "(?" in value or re.search(r"\\[1-9]", value):
        raise ReviewToolError("UNSAFE_REGEX", "lookarounds and backreferences are not allowed")
    if re.search(r"\)[*+?{]", value) or re.search(r"[*+?}]\s*[*+?{]", value):
        raise ReviewToolError("UNSAFE_REGEX", "nested or grouped quantifiers are not allowed")
    if value.count(".*") + value.count(".+") > 2:
        raise ReviewToolError("UNSAFE_REGEX", "too many unbounded wildcard quantifiers")


def _path_summary(value: str) -> dict[str, Any]:
    path = PurePosixPath(value)
    return {
        "pathHash": hashlib.sha256(value.encode("utf-8")).hexdigest()[:16],
        "suffix": path.suffix.casefold()[:20],
        "depth": len(path.parts),
    }


def _read_text_lines(path: Path, max_file_bytes: int) -> list[str]:
    if path.stat().st_size > max_file_bytes:
        raise ReviewToolError("FILE_TOO_LARGE", "file exceeds the maximum readable size")
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        raise ReviewToolError("BINARY_FILE", "binary files are not readable")
    return data.decode("utf-8", errors="replace").splitlines()
