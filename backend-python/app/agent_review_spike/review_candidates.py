from __future__ import annotations

from collections import Counter
from concurrent.futures import Future
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from pydantic import ValidationError

from app.agent_review_spike.finding_anchor import (
    ANCHOR_WAIT_SECONDS, MAX_CANDIDATES, AnchorPool, AnchorQuote, AnchorResult, FindingAnchorIndex,
)
from app.agent_review_spike.schema import finding_identity, validate_review_card
from app.agent_review_spike.workspace import ReviewToolError, validate_review_path


@dataclass
class _Candidate:
    path: str
    title: str
    body: str
    outcome: AnchorResult | Future[AnchorResult] | None
    status: str | None = None


class ReviewCandidates:
    """Candidate identifiers and model-provided anchors belong to a single review pass."""

    def __init__(
        self, paths: set[str], index: FindingAnchorIndex, pool: AnchorPool, publish: Callable[[], None],
    ) -> None:
        self.paths = paths
        self.index = index
        self.pool = pool
        self.publish = publish
        self.candidates: dict[str, _Candidate] = {}
        self.references: dict[tuple[Any, ...], dict[str, Any]] = {}

    def submit_candidate(self, args: dict[str, Any]) -> dict[str, Any]:
        if len(self.candidates) >= MAX_CANDIDATES:
            raise ReviewToolError("CANDIDATE_LIMIT", "Pass candidate limit reached; use submit_review")
        raw_path = args.get("filePath")
        if not isinstance(raw_path, str):
            raise ReviewToolError("INVALID_CANDIDATE", "A candidate requires a changed file path")
        path = validate_review_path(raw_path)
        if path not in self.paths:
            raise ReviewToolError("INVALID_CANDIDATE", "The candidate must belong to this review group")
        title, body = args.get("title"), args.get("body")
        if (not isinstance(title, str) or not title.strip() or len(title) > 160
                or not isinstance(body, str) or not body.strip() or len(body) > 320):
            raise ReviewToolError("INVALID_CANDIDATE", "Supply a short candidate title and description")
        candidate_id = uuid4().hex
        outcome = self._start(path, args["anchorQuote"]) if "anchorQuote" in args else None
        self.candidates[candidate_id] = _Candidate(path, title, body, outcome)
        self.publish()
        return {"candidateId": candidate_id}

    def validate_submission(self, card: dict[str, Any], changed_files: list[str]) -> dict[str, Any]:
        originals = card.get("findings")
        if not isinstance(originals, list):
            return validate_review_card(card, changed_files)
        metadata = {"anchorQuote", "candidateId"}
        cleaned = {**card, "findings": [
            {key: value for key, value in raw.items() if key not in metadata} if isinstance(raw, dict) else raw
            for raw in originals[:51]
        ]}
        indices: list[int] = []
        result = validate_review_card(cleaned, changed_files, accepted_indices=indices)
        self.references = {
            finding_identity(finding): values
            for finding, index in zip(result["findings"], indices, strict=True)
            if (values := {key: originals[index][key] for key in metadata if key in originals[index]})
        }
        return result

    def snapshot(self) -> list[dict[str, Any]]:
        output = []
        for candidate_id, candidate in self.candidates.items():
            outcome = _outcome(candidate.outcome)
            status = candidate.status
            if status is None:
                if outcome:
                    status = "LOCATED" if outcome.location else "UNLOCATED"
                else:
                    status = "PENDING_LOCATION" if candidate.outcome else "UNLOCATED"
            output.append({
                "candidateId": candidate_id, "filePath": candidate.path, "title": candidate.title,
                "body": candidate.body, "status": status,
                **({"anchor": outcome.model_dump(exclude_none=True)} if outcome else {}),
            })
        return output

    def discard(self) -> None:
        for candidate in self.candidates.values():
            candidate.status = "DISCARDED"
            candidate.outcome = self._finish(candidate.outcome)

    def settle(
        self, findings: dict[tuple[Any, ...], dict[str, Any]], remaining: float,
    ) -> dict[tuple[Any, ...], AnchorResult]:
        deadline = monotonic() + min(ANCHOR_WAIT_SECONDS, max(remaining, 0))
        counts = Counter(
            meta["candidateId"] for meta in self.references.values() if isinstance(meta.get("candidateId"), str)
        )
        outcomes = {}
        fallbacks = {}
        for identity, finding in findings.items():
            if not (meta := self.references.get(identity)):
                continue
            candidate_id = meta.get("candidateId")
            candidate = self.candidates.get(candidate_id) if isinstance(candidate_id, str) else None
            path = finding["filePath"]
            if candidate and candidate.path == path and counts[candidate_id] == 1:
                candidate.status = "FINISHED"
                outcomes[identity] = candidate.outcome
                if "anchorQuote" in meta:
                    fallbacks[identity] = (path, meta["anchorQuote"])
            elif "anchorQuote" in meta:
                outcomes[identity] = self._start_before(deadline, path, meta["anchorQuote"])
            else:
                outcomes[identity] = AnchorResult(status="UNAVAILABLE", reasonCode="INVALID_CANDIDATE")
        for candidate in self.candidates.values():
            if candidate.status != "FINISHED":
                candidate.status = "DISCARDED"
                if isinstance(candidate.outcome, Future):
                    candidate.outcome.cancel()
        self._wait(outcomes, deadline)
        fallback_outcomes = {
            identity: self._start_before(deadline, *fallback)
            for identity, fallback in fallbacks.items()
            if not ((outcome := _outcome(outcomes[identity])) and outcome.location)
        }
        self._wait(fallback_outcomes, deadline)
        for identity, fallback in fallback_outcomes.items():
            if (result := _outcome(fallback)) and result.reasonCode not in {"TIME_BUDGET", "CANCELLED", "QUEUE_FULL"}:
                outcomes[identity] = result
            elif outcomes[identity] is None:
                outcomes[identity] = fallback
        for candidate in self.candidates.values():
            candidate.outcome = self._finish(candidate.outcome)
        return {
            identity: result
            for identity, outcome in outcomes.items()
            if (result := self._finish(outcome)) is not None
        }

    def _start_before(self, deadline: float, path: str, quote: Any) -> Future[AnchorResult] | AnchorResult:
        if monotonic() >= deadline:
            return AnchorResult(status="UNAVAILABLE", reasonCode="TIME_BUDGET")
        return self._start(path, quote)

    def _start(self, path: str, value: Any) -> Future[AnchorResult] | AnchorResult:
        try:
            quote = AnchorQuote.model_validate(value)
        except ValidationError:
            return AnchorResult(status="UNAVAILABLE", reasonCode="INVALID_QUOTE")
        future = self.pool.submit(self.index, path, quote)
        if future is not None:
            return future
        reason = "CANCELLED" if self.pool.cancelled.is_set() else "QUEUE_FULL"
        return AnchorResult(status="UNAVAILABLE", reasonCode=reason)

    def _wait(self, outcomes: dict[tuple[Any, ...], Any], deadline: float) -> None:
        self.pool.await_results({value for value in outcomes.values() if isinstance(value, Future)}, deadline)

    def _finish(self, outcome: AnchorResult | Future[AnchorResult] | None) -> AnchorResult | None:
        result = _outcome(outcome)
        if result is None and isinstance(outcome, Future):
            outcome.cancel()
            reason = "CANCELLED" if self.pool.cancelled.is_set() else "TIME_BUDGET"
            return AnchorResult(status="UNAVAILABLE", reasonCode=reason)
        return result


def _outcome(value: AnchorResult | Future[AnchorResult] | None) -> AnchorResult | None:
    if not isinstance(value, Future):
        return value
    if not value.done() or value.cancelled():
        return None
    try:
        return value.result()
    except Exception:
        return AnchorResult(status="UNAVAILABLE", reasonCode="LOCATION_FAILED")
