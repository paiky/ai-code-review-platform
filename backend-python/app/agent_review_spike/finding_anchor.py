from __future__ import annotations

from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import re
from threading import BoundedSemaphore, Event, Lock
from time import monotonic
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.agent_review_spike.diff import DiffSection, owned_diff_sections


MAX_CANDIDATES = 50
ANCHOR_WAIT_SECONDS = 0.5
_ANCHOR_WORKERS = 2
_ANCHOR_CAPACITY = 64
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
Side = Literal["OLD", "NEW"]


class AnchorQuote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: str = Field(min_length=1, max_length=600)
    side: Side | None = None

    @model_validator(mode="after")
    def require_text(self) -> AnchorQuote:
        if not self.text.strip():
            raise ValueError("An anchor quote must contain source text")
        return self


class AnchorLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    filePath: str = Field(min_length=1, max_length=1024)
    side: Side
    startLine: int = Field(ge=1, lt=2**31)
    endLine: int = Field(ge=1, lt=2**31)

    @model_validator(mode="after")
    def validate_range(self) -> AnchorLocation:
        if self.endLine < self.startLine:
            raise ValueError("Invalid anchor range")
        return self


class AnchorResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["MATCHED", "AMBIGUOUS", "UNMATCHED", "UNAVAILABLE"]
    location: AnchorLocation | None = None
    reasonCode: Literal[
        "MISSING_DIFF", "INVALID_QUOTE", "INVALID_CANDIDATE", "QUEUE_FULL",
        "TIME_BUDGET", "CANCELLED", "LOCATION_FAILED",
    ] | None = None

    @model_validator(mode="after")
    def validate_result(self) -> AnchorResult:
        if (self.status == "MATCHED") != (self.location is not None):
            raise ValueError("Only matched anchors have a location")
        if (self.status == "UNAVAILABLE") != (self.reasonCode is not None):
            raise ValueError("Unavailable anchors require a reason code")
        return self


class AnchorCompletion(AnchorResult):
    findingIndex: int = Field(ge=0, lt=50)
    groupId: int = Field(ge=1, le=250)
    passNo: int = Field(ge=1, le=3)


@dataclass(frozen=True)
class _SideHunk:
    path: str
    side: Side
    start: int
    line_count: int
    text: str


class FindingAnchorIndex:
    """Index each owned patch once on its first lookup, including across passes."""

    def __init__(self, sections: dict[str, DiffSection]) -> None:
        self._sections = sections
        self._locks = {path: Lock() for path in sections}
        self._hunks: dict[str, tuple[_SideHunk, ...]] = {}

    def _for_file(self, file_path: str) -> tuple[_SideHunk, ...]:
        lock = self._locks.get(file_path)
        if lock is None:
            return ()
        with lock:
            if file_path not in self._hunks:
                self._hunks[file_path] = _index_patch(self._sections[file_path], file_path)
            return self._hunks[file_path]

    def locate(self, file_path: str, quote: AnchorQuote) -> AnchorResult:
        hunks = self._for_file(file_path)
        if not hunks:
            return AnchorResult(status="UNAVAILABLE", reasonCode="MISSING_DIFF")
        needle = quote.text.replace("\r\n", "\n").strip("\n")
        line_count = needle.count("\n") + 1
        needle = f"\n{needle}\n"
        matches: dict[tuple[str, int, int], Side] = {}
        for hunk in hunks:
            if quote.side is not None and quote.side != hunk.side:
                continue
            offset = hunk.text.find(needle)
            while offset >= 0:
                start = hunk.start + hunk.text.count("\n", 0, offset)
                key = (hunk.path, start, start + line_count - 1)
                matches[key] = "NEW" if hunk.side == "NEW" else matches.get(key, "OLD")
                if len(matches) > 1:
                    return AnchorResult(status="AMBIGUOUS")
                offset = hunk.text.find(needle, offset + 1)
        if not matches:
            return AnchorResult(status="UNMATCHED")
        (path, start, end), side = next(iter(matches.items()))
        return AnchorResult(status="MATCHED", location=AnchorLocation(
            filePath=path, side=side, startLine=start, endLine=end,
        ))

    def contains(self, file_path: str, location: AnchorLocation) -> bool:
        return any(
            hunk.path == location.filePath and hunk.side == location.side
            and hunk.start <= location.startLine <= location.endLine < hunk.start + hunk.line_count
            for hunk in self._for_file(file_path)
        )


def _index_patch(section: DiffSection, file_path: str) -> tuple[_SideHunk, ...]:
    old_path = section.old_path
    if old_path is None and section.text.startswith("@@ "):
        old_path = file_path
    lines = section.patch.split("\n")
    headers = [(index, match) for index, line in enumerate(lines) if (match := _HUNK.match(line))]
    if not headers:
        return ()
    hunks = []
    for (index, match), end in zip(headers, [*(index for index, _ in headers[1:]), len(lines)], strict=True):
        old, new = [], []
        for line in lines[index + 1 : end]:
            if line.startswith((" ", "-")):
                old.append(line[1:])
            if line.startswith((" ", "+")):
                new.append(line[1:])
            if not line.startswith((" ", "-", "+", "\\ No newline at end of file")):
                return ()
        if len(old) != int(match[2] or 1) or len(new) != int(match[4] or 1):
            return ()
        old_start, new_start = int(match[1]), int(match[3])
        if (old and not 1 <= old_start <= 2**31 - len(old)
                or new and not 1 <= new_start <= 2**31 - len(new)):
            return ()
        if old and old_path:
            hunks.append(_SideHunk(old_path, "OLD", old_start, len(old), "\n" + "\n".join(old) + "\n"))
        if new and section.new_path:
            hunks.append(_SideHunk(section.new_path, "NEW", new_start, len(new), "\n" + "\n".join(new) + "\n"))
    return tuple(hunks)


def attach_finding_anchors(
    findings: list[dict[str, Any]], value: Any, coverage: list[dict[str, Any]], diff: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 50:
        return findings
    group_paths = {group["groupId"]: set(group["paths"]) for group in coverage}
    paths = {path for group in group_paths.values() for path in group}
    index = FindingAnchorIndex(owned_diff_sections(diff, list(paths), unified=True))
    indices = Counter(
        item["findingIndex"] for item in value
        if isinstance(item, dict) and type(item.get("findingIndex")) is int
    )
    result = list(findings)
    for item in value:
        try:
            anchor = AnchorCompletion.model_validate(item)
        except ValidationError:
            continue
        number = anchor.findingIndex
        if number >= len(findings) or indices[number] != 1:
            continue
        finding = findings[number]
        if finding["filePath"] not in group_paths.get(anchor.groupId, ()):
            continue
        if anchor.location and not index.contains(finding["filePath"], anchor.location):
            continue
        result[number] = {**finding, "anchor": anchor.model_dump(
            exclude_none=True, exclude={"findingIndex", "groupId", "passNo"},
        )}
    return result


class AnchorPool:
    def __init__(self, cancelled: Event) -> None:
        self.cancelled = cancelled
        self._executor = ThreadPoolExecutor(max_workers=_ANCHOR_WORKERS, thread_name_prefix="finding-anchor")
        self._capacity = BoundedSemaphore(_ANCHOR_CAPACITY)

    def submit(self, index: FindingAnchorIndex, path: str, quote: AnchorQuote) -> Future[AnchorResult] | None:
        if self.cancelled.is_set() or not self._capacity.acquire(blocking=False):
            return None
        try:
            future = self._executor.submit(index.locate, path, quote)
        except BaseException:
            self._capacity.release()
            raise
        future.add_done_callback(lambda _: self._capacity.release())
        return future

    def await_results(self, futures: set[Future[AnchorResult]], deadline: float) -> None:
        pending = futures
        while pending and not self.cancelled.is_set():
            remaining = deadline - monotonic()
            if remaining <= 0:
                return
            _, pending = wait(pending, timeout=min(remaining, 0.05))

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
