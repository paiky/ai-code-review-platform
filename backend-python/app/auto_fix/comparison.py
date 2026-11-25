from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class _Edit:
    old_start: int
    old_end: int
    new_start: int
    new_end: int


def _edits(diff: str) -> list[_Edit] | None:
    edits = []
    lines = diff.split("\n")
    cursor = 0
    while cursor < len(lines):
        header = _HUNK.match(lines[cursor])
        cursor += 1
        if header is None:
            continue
        old_start, old_count, new_start, new_count = header.groups()
        old_remaining = 1 if old_count is None else int(old_count)
        new_remaining = 1 if new_count is None else int(new_count)
        old_line = int(old_start) + (old_remaining == 0)
        new_line = int(new_start) + (new_remaining == 0)
        edit_start = None
        while old_remaining or new_remaining:
            if cursor >= len(lines):
                return None
            marker = lines[cursor][:1]
            cursor += 1
            if marker == "\\":
                continue
            if marker not in {" ", "-", "+"}:
                return None
            if marker == " ":
                if edit_start is not None:
                    edits.append(_Edit(edit_start[0], old_line, edit_start[1], new_line))
                    edit_start = None
            elif edit_start is None:
                edit_start = (old_line, new_line)
            if marker != "+":
                old_line += 1
                old_remaining -= 1
            if marker != "-":
                new_line += 1
                new_remaining -= 1
            if old_remaining < 0 or new_remaining < 0:
                return None
        if edit_start is not None:
            edits.append(_Edit(edit_start[0], old_line, edit_start[1], new_line))
    return edits or None


def _position(line: int, edits: list[_Edit]) -> tuple[int, int] | None:
    offset = 0
    for edit in edits:
        if line < edit.old_start:
            break
        if line < edit.old_end:
            if edit.new_start == edit.new_end:
                return None
            return edit.new_start, edit.new_end - 1
        offset = edit.new_end - edit.old_end
    return line + offset, line + offset


def _span(finding: dict[str, Any]) -> tuple[int, int] | None:
    start = finding.get("startLine")
    end = finding.get("endLine") or start
    if type(start) is not int or type(end) is not int or not 1 <= start <= end:
        return None
    return start, end


def _norm(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _identity(finding: dict[str, Any]) -> tuple[str, str]:
    path = str(finding.get("filePath") or "").removeprefix("./")
    return path, _norm(finding.get("category"))


def _shares_evidence(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    previous_title = _norm(previous.get("title"))
    if previous_title and previous_title == _norm(current.get("title")):
        return True
    previous_evidence = previous.get("evidence")
    current_evidence = current.get("evidence")
    if not isinstance(previous_evidence, list) or not isinstance(current_evidence, list):
        return False
    left = {_norm(item) for item in previous_evidence if isinstance(item, str)}
    right = {_norm(item) for item in current_evidence if isinstance(item, str)}
    return bool((left & right) - {""})


def _severity(finding: dict[str, Any]) -> str | None:
    return str(finding.get("severity") or "").strip().upper() or None


def compare_findings(
    previous: Sequence[dict[str, Any]],
    current: Sequence[dict[str, Any]],
    file_diffs: Mapping[str, str],
    *,
    complete: bool,
    reviewed_paths: Collection[str],
) -> list[dict[str, Any]]:
    def row(
        status: str, reason_code: str, old: int | None, new: int | None, **details: Any,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "reasonCode": reason_code,
            "previousIndex": old,
            "currentIndex": new,
            "previousSeverity": _severity(previous[old]) if old is not None else None,
            "currentSeverity": _severity(current[new]) if new is not None else None,
            **details,
        }

    if not complete:
        return [
            *[row("UNDETERMINED", "REVIEW_INCOMPLETE", index, None) for index in range(len(previous))],
            *[row("UNDETERMINED", "REVIEW_INCOMPLETE", None, index) for index in range(len(current))],
        ]

    candidates_by_file = defaultdict(list)
    for index, finding in enumerate(current):
        candidates_by_file[_identity(finding)].append(index)

    edits_by_file = {path: _edits(diff) for path, diff in file_diffs.items()}
    weak_current = defaultdict(list)
    weak_previous = defaultdict(list)
    strong_current = defaultdict(list)
    strong_previous = defaultdict(list)
    unclear = set()
    removed = set()
    for old_index, old_finding in enumerate(previous):
        path, category = _identity(old_finding)
        old_span = _span(old_finding)
        edits = edits_by_file.get(path, [])
        if not path or not category or old_span is None or edits is None:
            unclear.add(old_index)
            mapped = None
        else:
            first = _position(old_span[0], edits)
            last = _position(old_span[1], edits)
            if first is None and last is None and any(
                edit.old_start <= old_span[0] <= old_span[1] < edit.old_end
                and edit.new_start == edit.new_end
                for edit in edits
            ):
                removed.add(old_index)
            elif first is None or last is None:
                unclear.add(old_index)
            mapped = (first[0], last[1]) if first is not None and last is not None else None
        for new_index in candidates_by_file[(path, category)]:
            new_finding = current[new_index]
            new_span = _span(new_finding)
            overlaps = (
                mapped is not None and new_span is not None
                and mapped[0] <= new_span[1] and new_span[0] <= mapped[1]
            )
            same_evidence = _shares_evidence(old_finding, new_finding)
            if overlaps or same_evidence:
                weak_current[old_index].append(new_index)
                weak_previous[new_index].append(old_index)
            if overlaps and same_evidence:
                strong_current[old_index].append(new_index)
                strong_previous[new_index].append(old_index)

    results = []
    paired_current = set()
    for old_index, finding in enumerate(previous):
        path, _ = _identity(finding)
        strong = strong_current[old_index]
        if len(strong) == 1 and len(strong_previous[strong[0]]) == 1:
            new_index = strong[0]
            paired_current.add(new_index)
            results.append(row("PERSISTS", "EVIDENCE_AND_LOCATION_MATCH", old_index, new_index))
        elif weak_current[old_index] or old_index in unclear or path not in reviewed_paths:
            reason = "AMBIGUOUS_MATCH" if weak_current[old_index] else "INSUFFICIENT_FILE_EVIDENCE"
            results.append(row(
                "NEEDS_VERIFICATION", reason, old_index, None,
                candidateCurrentIndexes=weak_current[old_index],
            ))
        else:
            reason = "OLD_RANGE_REMOVED" if old_index in removed else "NO_REVIEW_MATCH"
            results.append(row("NOT_REOBSERVED", reason, old_index, None))

    for new_index, finding in enumerate(current):
        if new_index in paired_current:
            continue
        path, category = _identity(finding)
        if weak_previous[new_index] or path not in reviewed_paths or not category or _span(finding) is None:
            reason = "AMBIGUOUS_MATCH" if weak_previous[new_index] else "INSUFFICIENT_FILE_EVIDENCE"
            results.append(row(
                "NEEDS_VERIFICATION", reason, None, new_index,
                candidatePreviousIndexes=weak_previous[new_index],
            ))
        else:
            results.append(row("NEW", "NO_PREVIOUS_MATCH", None, new_index))
    return results


def same_critical_findings(
    previous: Sequence[dict[str, Any]],
    current: Sequence[dict[str, Any]],
    comparisons: Sequence[dict[str, Any]],
) -> bool:
    previous_critical = {index for index, finding in enumerate(previous) if _severity(finding) == "CRITICAL"}
    current_critical = {index for index, finding in enumerate(current) if _severity(finding) == "CRITICAL"}
    paired = [
        item for item in comparisons
        if item["status"] == "PERSISTS"
        and item["previousIndex"] in previous_critical
        and item["currentIndex"] in current_critical
    ]
    return (
        bool(previous_critical)
        and {item["previousIndex"] for item in paired} == previous_critical
        and {item["currentIndex"] for item in paired} == current_critical
        and len(paired) == len(previous_critical) == len(current_critical)
    )
