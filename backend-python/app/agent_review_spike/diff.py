from __future__ import annotations

import codecs
from dataclasses import dataclass
import re
from typing import Any

from app.agent_review_spike.workspace import ReviewToolError, validate_review_path


_GIT_HEADER = "diff --git "
_PLATFORM_HEADER = "diff -- "
_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
_QUOTED_PATH = re.compile(r'"(?:[^"\\]|\\(?:[0-7]{3}|[abtnvfr"\\]))*"')
_GIT_PATH_SEPARATOR = re.compile(r' (?=b/|"|/dev/null)')


def with_diff_section_header(
    path: str, patch: str, *, old_path: str | None = None, deleted: bool = False, added: bool = False,
) -> str:
    if patch.startswith((_GIT_HEADER, _PLATFORM_HEADER)):
        return patch
    # Unified headers carry their own old and new path identities.
    first, _, remaining = patch.partition("\n")
    if first.startswith("+++ ") or (first.startswith("--- ") and remaining.startswith("+++ ")):
        return f"diff -- {path}\n{patch}"
    old = _quote_git_path(f"a/{old_path or path}")
    new = _quote_git_path(f"b/{path}")
    old_header = "/dev/null" if added else old
    new_header = "/dev/null" if deleted else new
    return f"diff --git {old} {new}\n--- {old_header}\n+++ {new_header}\n{patch}"


@dataclass(frozen=True)
class DiffSection:
    old_path: str | None
    new_path: str | None
    text: str
    patch: str

    def changed_path(self, changed_files: set[str]) -> str | None:
        if self.new_path in changed_files:
            return self.new_path
        if self.old_path in changed_files:
            return self.old_path
        return None


def diff_by_file(case: dict[str, Any]) -> dict[str, str]:
    changed = {str(item).replace("\\", "/") for item in case.get("changedFiles") or []}
    single_path = next(iter(changed)) if len(changed) == 1 else None
    result: dict[str, str] = {}
    for section in split_diff_sections(str(case.get("diff") or ""), unheaded_path=single_path):
        path = section.changed_path(changed)
        if path and section.patch and path not in result:
            result[path] = section.patch
    return result


def split_diff_sections(diff_text: str, *, unheaded_path: str | None = None) -> list[DiffSection]:
    lines = [line.removesuffix("\r") for line in diff_text.split("\n")]
    boundaries = [0]
    old_remaining = new_remaining = 0
    has_headers = has_patch = False
    paired_new_header = -1
    # File markers can appear in hunk content. Only recognize header pairs outside it.
    for index, line in enumerate(lines):
        explicit_boundary = line.startswith((_GIT_HEADER, _PLATFORM_HEADER))
        nested_git_header = (
            line.startswith(_GIT_HEADER)
            and index == boundaries[-1] + 1
            and lines[index - 1].startswith(_PLATFORM_HEADER)
        )
        header_pair = (
            not (old_remaining or new_remaining)
            and line.startswith("--- ")
            and index + 1 < len(lines)
            and lines[index + 1].startswith("+++ ")
        )
        single_new_header = (
            not (old_remaining or new_remaining)
            and line.startswith("+++ ")
            and index != paired_new_header
        )
        if (explicit_boundary and not nested_git_header) or (
            (header_pair or single_new_header) and (has_headers or has_patch)
        ):
            if index:
                boundaries.append(index)
            old_remaining = new_remaining = 0
            has_headers = has_patch = False
        if header_pair:
            paired_new_header = index + 1
        if header_pair or single_new_header:
            has_headers = True
        if hunk := _HUNK.match(line):
            old_remaining = int(hunk[1] or "1")
            new_remaining = int(hunk[2] or "1")
            has_patch = True
            continue
        marker = line[:1]
        if not header_pair and index != paired_new_header and marker in {"+", "-"}:
            has_patch = has_patch or not line.startswith(("+++ ", "--- "))
        if marker in {"-", " "} and old_remaining:
            old_remaining -= 1
        if marker in {"+", " "} and new_remaining:
            new_remaining -= 1

    sections: list[DiffSection] = []
    # An unheaded patch is usable only when the whole input has one provable owner.
    fallback = unheaded_path if len(boundaries) == 1 else None
    for start, end in zip(boundaries, (*boundaries[1:], len(lines))):
        section = _parse_section(lines[start:end], fallback)
        if section is not None:
            sections.append(section)
    return sections


def _parse_section(lines: list[str], unheaded_path: str | None) -> DiffSection | None:
    text = "\n".join(lines).strip("\n")
    if not text:
        return None
    first_line = lines[0]
    platform_path = first_line.removeprefix(_PLATFORM_HEADER) if first_line.startswith(_PLATFORM_HEADER) else None
    git_line = lines[1] if platform_path is not None and len(lines) > 1 else first_line
    git_header = git_line.removeprefix(_GIT_HEADER) if git_line.startswith(_GIT_HEADER) else None
    old_path = new_path = None
    patch_start = header_index = None
    for index, line in enumerate(lines):
        if _HUNK.match(line):
            patch_start = index
            break
        if line.startswith("--- ") and index + 1 < len(lines) and lines[index + 1].startswith("+++ "):
            old_path = _path_field(line[4:], prefix="a/")
            new_path = _path_field(lines[index + 1][4:], prefix="b/")
            if old_path is None or new_path is None:
                return None
            header_index = index + 1
        elif line.startswith("+++ ") and header_index is None:
            new_path = _path_field(line[4:], prefix="b/")
            if new_path is None:
                return None
            header_index = index
        elif line.startswith(("Binary files ", "GIT binary patch")):
            break
        elif line.startswith(("+", "-")) and not line.startswith(("+++ ", "--- ")):
            patch_start = index
            break

    if git_header is not None:
        paths = _git_header_paths(git_header, old_path, new_path)
        if paths is None:
            return None
        git_old_path, git_new_path = paths
        old_path = git_old_path if old_path is None else old_path
        new_path = git_new_path if new_path is None else new_path
    if platform_path is not None:
        platform_path = _safe_path(platform_path)
        if platform_path is None or (old_path or new_path) and platform_path not in {old_path, new_path}:
            return None
        if old_path is None and new_path is None:
            new_path = platform_path
    if old_path is None and new_path is None and patch_start is not None:
        new_path = _safe_path(unheaded_path)
    if not (old_path or new_path):
        return None

    patch = ""
    if patch_start is not None:
        start = header_index if header_index is not None else patch_start
        patch = "\n".join(lines[start:]).rstrip("\n")
    return DiffSection(old_path or None, new_path or None, text, patch)


def _git_header_paths(raw: str, old_path: str | None, new_path: str | None) -> tuple[str, str] | None:
    candidates = []
    expected_old = new_path if old_path == "" else old_path
    expected_new = old_path if new_path == "" else new_path
    for separator in _GIT_PATH_SEPARATOR.finditer(raw):
        old = _path_field(raw[: separator.start()], prefix="a/", git_header=True)
        new = _path_field(raw[separator.end() :], prefix="b/", git_header=True)
        if old is None or new is None:
            continue
        # Git repeats the surviving path in diff --git. Older producers may use /dev/null there.
        if expected_old is not None and old != expected_old and not (old_path == "" and old == ""):
            continue
        if expected_new is not None and new != expected_new and not (new_path == "" and new == ""):
            continue
        if old or new:
            candidates.append((old, new))
    if len(candidates) == 1:
        return candidates[0]
    same_path = [pair for pair in candidates if pair[0] == pair[1]]
    return same_path[0] if len(same_path) == 1 else None


def _path_field(raw: str, *, prefix: str, git_header: bool = False) -> str | None:
    if git_header and "\t" in raw:
        return None
    field = raw.split("\t", 1)[0]
    if field.startswith('"'):
        if not _QUOTED_PATH.fullmatch(field):
            return None
        try:
            field = codecs.escape_decode(field[1:-1].encode("utf-8"))[0].decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return None
    if field == "/dev/null":
        return ""
    if field.startswith(prefix):
        field = field[len(prefix) :]
    elif git_header:
        return None
    return _safe_path(field)


def _safe_path(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return validate_review_path(path)
    except ReviewToolError:
        return None


def _quote_git_path(path: str) -> str:
    if not any(char in path for char in '\\"\t\r\n'):
        return path
    escaped = path.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")
    return f'"{escaped}"'
