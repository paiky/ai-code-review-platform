from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Literal

from app.agent_review.schemas import (
    AGENT_CONVERSATION_INPUT,
    AGENT_CONVERSATION_TURN,
    OPENAI_RESPONSES_SUMMARY_SOURCE,
    AgentConversationEvent,
    AgentConversationInputEvent,
    AgentConversationSummaryKind,
    AgentConversationTurnEvent,
    AgentRuntimeProtocol,
)
from app.agent_review_spike.budgets import AGENT_BUDGET_LIMITS
from app.agent_review_spike.prompting import AGENT_SYSTEM_TEMPLATE
from app.agent_review_spike.tool_executor import ToolExecutionResult
from app.review_prompt_metadata import PlatformPromptMarker, ReviewInputSource, ReviewProfileInput


ConversationCallback = Callable[[list[dict[str, Any]]], None]
_CODE_TOOLS = {"search_code", "read_file_range", "read_diff_range"}
_MAX_REQUEST_MS = AGENT_BUDGET_LIMITS["timeoutSeconds"]["max"] * 1000
_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_EvidenceKey = tuple[str, str, int, bytes]


@dataclass(frozen=True)
class AgentReviewProgress:
    audit: Callable[[dict[str, Any]], None]
    conversation: ConversationCallback

    def __call__(self, snapshot: dict[str, Any]) -> None:
        self.audit(snapshot)


class ConversationCapture:
    """Publish replay facts without retaining model messages or tool content in events."""

    def __init__(
        self,
        protocol: AgentRuntimeProtocol | Literal["ANTHROPIC_COMPATIBLE"],
        case: dict[str, Any],
        diff_by_file: dict[str, str],
        callback: ConversationCallback | None,
        submit_by_turn: int,
    ) -> None:
        self.protocol = protocol
        self.case = case
        self.diff_by_file = diff_by_file
        self.callback = callback
        self.submit_by_turn = submit_by_turn
        self.diff_mode = (
            "TOOL_PAGED" if str(case.get("diffMode")).upper() == "TOOL_PAGED" else "INLINE"
        )
        self.events: list[AgentConversationEvent] = []
        self.pending_input: AgentConversationInputEvent | None = None
        self.seen: set[_EvidenceKey] = set()
        self.seeded = False
        self.audit_offset = 0
        self.stall_turns = 0
        self.retrieved = False
        self.measurement_available = True
        self.new_evidence_count = 0

    def prepare_request(self, payload: dict[str, Any] | None = None) -> None:
        if self.callback is None or self.events:
            return
        try:
            # Match the HTTP transport's JSON body encoding.
            request_bytes = len(json.dumps(
                payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")) if payload is not None else None
            diff_bytes = (
                len(self.case["diff"].encode("utf-8")) if self.diff_mode == "INLINE" else 0
            )
            changed_file_count = len(self.case["changedFiles"])
            sources = [
                ReviewInputSource(source="PLATFORM_INSTRUCTIONS"),
                ReviewInputSource(source="CHANGED_FILES", count=changed_file_count),
                ReviewInputSource(source="DIFF", bytes=diff_bytes),
            ]
            if context := self.case.get("baselineContext"):
                sources.append(ReviewInputSource(source="BASELINE_CONTEXT", bytes=len(context.encode("utf-8"))))
            profile = None
            if raw_profile := self.case.get("profileInput"):
                profile = ReviewProfileInput.model_validate(raw_profile)
            sources.extend(ReviewInputSource.model_validate(item) for item in self.case.get("inputSources", []))
            self.pending_input = AgentConversationInputEvent(
                phase=AGENT_CONVERSATION_INPUT,
                schemaVersion=1,
                protocol=self.protocol,
                diffMode=self.diff_mode,
                changedFileCount=changed_file_count,
                requestBytes=request_bytes,
                diffBytes=diff_bytes,
                profile=profile,
                sourceSummaries=sources,
            )
        except (TypeError, ValueError):
            # Capture is optional and must not change transport or review outcomes.
            return

    def record_request(self) -> None:
        if self.pending_input is not None:
            event = self.pending_input
            self.pending_input = None
            self.events.append(event)
            try:
                self.events.append(PlatformPromptMarker(
                    templateId=AGENT_SYSTEM_TEMPLATE,
                    source="CLAUDE_CLI_APPEND" if self.protocol == "ANTHROPIC_COMPATIBLE" else "AGENT_HTTP",
                    protocol=self.protocol,
                    submitByTurn=self.submit_by_turn,
                ))
            except ValueError:
                pass
            self._notify()

    def record_tool(self, tool: str, result: ToolExecutionResult) -> None:
        if self.callback is None or tool not in _CODE_TOOLS:
            return
        self.retrieved = True
        if result.is_error or not self.measurement_available:
            return
        try:
            if not self.seeded:
                self.seeded = True
                if self.diff_mode == "INLINE":
                    for path, diff in self.diff_by_file.items():
                        self.seen.update(
                            _line_key("source", path, line, content)
                            for _, line, content in _diff_lines(diff)
                            if line is not None
                        )
            for key in self._tool_evidence(tool, result.value):
                if key not in self.seen:
                    self.seen.add(key)
                    self.new_evidence_count += 1
        except (KeyError, TypeError, ValueError):
            self.measurement_available = False

    def finish_turn(
        self,
        turn: int,
        request_ms: int,
        usage: Any,
        audit: dict[str, Any],
        *,
        summary_kind: AgentConversationSummaryKind | None = None,
    ) -> None:
        if self.callback is None:
            return
        audit_events = audit.get("events", [])
        sequences = [event["sequence"] for event in audit_events[self.audit_offset :]]
        self.audit_offset = len(audit_events)
        measured = self.retrieved and self.measurement_available
        if measured:
            self.stall_turns = 0 if self.new_evidence_count else self.stall_turns + 1
        elif self.retrieved:
            self.stall_turns = 0
        try:
            self._publish(AgentConversationTurnEvent(
                phase=AGENT_CONVERSATION_TURN,
                schemaVersion=1,
                turn=turn,
                toolSequences=sequences,
                modelRequestMs=request_ms if request_ms <= _MAX_REQUEST_MS else None,
                usage=usage,
                evidenceStatus="MEASURED" if measured else "UNAVAILABLE",
                newEvidenceCount=self.new_evidence_count if measured else None,
                consecutiveNoNewEvidenceTurns=self.stall_turns if measured else None,
                summarySource=OPENAI_RESPONSES_SUMMARY_SOURCE if summary_kind else None,
                summaryKind=summary_kind,
            ))
        except ValueError:
            pass
        self.retrieved = False
        self.measurement_available = True
        self.new_evidence_count = 0

    def _publish(self, event: AgentConversationEvent) -> None:
        self.events.append(event)
        self._notify()

    def _notify(self) -> None:
        if self.callback is None:
            return
        try:
            self.callback([item.model_dump(exclude_none=True) for item in self.events])
        except Exception:
            # A Worker reporting failure must never fail a review.
            pass

    def _tool_evidence(self, tool: str, value: dict[str, Any]) -> Iterator[_EvidenceKey]:
        if tool == "search_code":
            for match in value["matches"]:
                yield _line_key("source", match["path"], match["line"], match["text"])
            return
        if not value["lineCount"]:
            return
        path = value["path"]
        start = value["startLine"]
        if tool == "read_file_range":
            for line_number, content in enumerate(value["content"].split("\n"), start):
                prefix, separator, text = content.partition(": ")
                if not separator or prefix != str(line_number):
                    raise ValueError("File evidence is missing its line coordinate")
                yield _line_key("source", path, line_number, text)
        elif self.diff_mode == "TOOL_PAGED":
            for offset, line_number, content in _diff_lines(self.diff_by_file[path]):
                if offset > value["endLine"]:
                    break
                if offset >= start:
                    if line_number is None:
                        yield _line_key("diff", path, offset, content)
                    else:
                        yield _line_key("source", path, line_number, content)


def _line_key(kind: str, path: str, line: int, content: str) -> _EvidenceKey:
    # Search returns at most the first 500 characters of a source line.
    comparable_content = content[:500] if kind == "source" else content
    digest = hashlib.blake2b(comparable_content.encode("utf-8"), digest_size=16).digest()
    return kind, path, line, digest


def _diff_lines(diff: str) -> Iterator[tuple[int, int | None, str]]:
    """Yield code-bearing diff offsets and new-side source coordinates when available."""
    old_remaining = new_remaining = new_line = 0
    for offset, content in enumerate(diff.split("\n"), 1):
        if header := _HUNK_HEADER.match(content):
            old_remaining = int(header[1] or "1")
            new_line = int(header[2])
            new_remaining = int(header[3] or "1")
            continue
        marker = content[:1]
        if marker == "-" and old_remaining:
            old_remaining -= 1
            yield offset, None, content
        elif marker in {"+", " "} and new_remaining:
            yield offset, new_line, content[1:]
            new_line += 1
            new_remaining -= 1
            if marker == " " and old_remaining:
                old_remaining -= 1
        elif marker in {"+", "-"} and not content.startswith(("+++ ", "--- ")):
            # Some patches lack a usable hunk header. Their diff coordinates are still stable.
            yield offset, None, content
