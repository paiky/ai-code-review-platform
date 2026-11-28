"""Run deterministic local acceptance for the finding anchor workflow."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import perf_counter
from typing import Any, Callable
from unittest.mock import patch

from app.agent_review.schemas import ContextReviewSettings
from app.agent_review_spike.chat_completions_runner import OpenAIChatCompletionsAgentRunner
from app.agent_review_spike.diff import owned_diff_sections, with_diff_section_header
from app.agent_review_spike.fact_check import FACT_CHECK_PROMPT
from app.agent_review_spike.finding_anchor import ANCHOR_WAIT_SECONDS, AnchorPool, AnchorQuote, FindingAnchorIndex
from app.agent_review_spike.grouped import run_grouped_review
from app.agent_review_spike.responses_runner import OpenAIResponsesAgentRunner
from app.agent_review_spike.review_candidates import ReviewCandidates
from app.agent_review_spike.schema import finding_identity
from app.agent_review_spike.synthetic_chat_completions_validation import _call, _response as chat_response
from app.agent_review_spike.synthetic_grouped_validation import GroupedSyntheticTransport
from app.agent_review_spike.synthetic_responses_validation import _response as responses_response


def fixture_case(paths: list[str], lines: int) -> dict[str, Any]:
    old = "\n".join(f"-old_{line} = True" for line in range(1, lines + 1))
    new = "\n".join(f"+flag_{line} = True" for line in range(1, lines + 1))
    return {
        "id": "finding-anchor-acceptance",
        "changedFiles": paths,
        "diff": "\n".join(with_diff_section_header(
            path, f"@@ -1,{lines} +1,{lines} @@\n{old}\n{new}",
        ) for path in paths),
    }


class AnchorTransport:
    def __init__(
        self, protocol: str, *, use_candidates: bool, lookup_started: Event | None = None,
        release_lookup: Event | None = None,
    ) -> None:
        self.protocol = protocol
        self.use_candidates = use_candidates
        self.lookup_started = lookup_started
        self.release_lookup = release_lookup
        self.candidate_ids: dict[tuple[str, bool], str] = {}
        self.checks: list[str] = []
        self.check_ready: Callable[[str], None] = lambda _: None
        self.turns: dict[tuple[str, bool], int] = {}

    def create(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        responses = self.protocol == "responses"
        history = payload.get("input") if responses else payload["messages"][1:]
        instructions = payload["instructions"] if responses else payload["messages"][0]["content"]
        if instructions == FACT_CHECK_PROMPT:
            raw = history if responses else history[0]["content"]
            records = json.loads(raw)["findings"]
            for record in records:
                self.check_ready(record["title"])
                self.checks.append(record["title"])
            text = json.dumps([
                {"findingId": record["findingId"], "verdict": "KEEP", "reason": "Fixture."}
                for record in records
            ])
            if responses:
                return responses_response(8, [{"type": "message", "content": [{"type": "output_text", "text": text}]}])
            return {"choices": [{"message": {"content": text}}], "usage": {"total_tokens": 15}}
        content = history[0]["content"]
        text = content[0]["text"] if responses else content
        path = next(line for line in text.splitlines() if line.startswith("Changed files:")).split("'")[1]
        next_pass = "Findings already reported for this group" in text
        key = (path, next_pass)
        turn = self.turns.get(key, 0) + 1
        self.turns[key] = turn
        quote = {"text": "flag_2 = True" if next_pass else "flag_1 = True", "side": "NEW"}
        finding = {
            **GroupedSyntheticTransport._finding(path),
            "title": f"{path} pass {2 if next_pass else 1}",
        }
        if self.use_candidates and turn == 1:
            tool = "submit_candidate"
            args = {"filePath": path, "title": finding["title"], "body": finding["body"], "anchorQuote": quote}
        elif turn == (2 if self.use_candidates else 1):
            if self.use_candidates:
                output = history[-1]["output" if responses else "content"]
                self.candidate_ids[key] = json.loads(output)["candidateId"]
                if self.lookup_started is not None and not next_pass:
                    assert self.lookup_started.wait(2)
                    assert self.release_lookup is not None and not self.release_lookup.is_set()
                    self.release_lookup.set()
            tool = "read_diff_range"
            args = {"path": path, "startLine": 1, "endLine": 5}
        else:
            tool = "submit_review"
            if self.use_candidates:
                finding["candidateId"] = self.candidate_ids[key]
            else:
                finding["anchorQuote"] = quote
            args = {"summary": "Finding anchor acceptance", "overallLevel": "HIGH", "findings": [finding]}
        call_id = f"call-{turn}"
        if responses:
            return responses_response(turn, [{
                "type": "function_call", "id": call_id, "call_id": call_id, "name": tool, "arguments": json.dumps(args),
            }])
        return chat_response(turn, [_call(call_id, tool, args)])


def run_fixture(
    protocol: str, case: dict[str, Any], *, use_candidates: bool, delayed: bool = False,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], dict[tuple[int, int], dict[str, Any]], float]:
    started_lookup, release_lookup = Event(), Event()
    transport = AnchorTransport(
        protocol, use_candidates=use_candidates,
        lookup_started=started_lookup if delayed else None,
        release_lookup=release_lookup if delayed else None,
    )
    runner = (
        OpenAIResponsesAgentRunner(transport) if protocol == "responses"
        else OpenAIChatCompletionsAgentRunner(transport)
    )
    snapshots = {}

    def on_progress(value: dict[str, Any]) -> None:
        snapshots[value["groupId"], value["passNo"]] = deepcopy(value)
        if progress:
            progress(value)

    def before_check(title: str) -> None:
        matches = [row for row in tuple(snapshots.values()) if any(finding["title"] == title for finding in row["findings"])]
        assert len(matches) == 1
        row = matches[0]
        assert row["anchorProgress"]["status"] == "COMPLETED"
        assert row["findings"][0]["anchor"]["status"] == "MATCHED"
        assert row["factCheck"]["status"] == "RUNNING"

    original = FindingAnchorIndex.locate

    def delayed_locate(index: FindingAnchorIndex, path: str, quote: AnchorQuote):
        if delayed and quote.text == "flag_1 = True":
            started_lookup.set()
            assert release_lookup.wait(2)
        return original(index, path, quote)

    transport.check_ready = before_check
    start = perf_counter()
    with TemporaryDirectory(prefix="finding-anchor-acceptance-") as name, patch.object(
        FindingAnchorIndex, "locate", delayed_locate,
    ):
        result = run_grouped_review(
            runner, case, Path(name), ContextReviewSettings(timeoutMinutesPerPass=-1),
            cancel_event=Event(), progress=lambda _: None, unified=True, on_pass_progress=on_progress,
        )
    expected = len(case["changedFiles"]) * 2
    assert result["status"] == "SUCCESS", result
    counts = (len(result["card"]["findings"]), len(result["anchorResults"]), len(transport.checks))
    assert counts == (expected,) * 3, (counts, result.get("factCheckResults"), result["groupCoverage"])
    assert all(row["location"]["startLine"] == row["passNo"] for row in result["anchorResults"])
    assert "anchorQuote" not in json.dumps(result["card"]) and "candidateId" not in json.dumps(result["card"])
    if use_candidates:
        assert all(row["candidates"][0]["status"] == "FINISHED" for row in snapshots.values())
    return result, snapshots, (perf_counter() - start) * 1000


def validate() -> dict[str, Any]:
    path = "src/changed.py"
    renamed = with_diff_section_header(
        path, "@@ -11,2 +21,2 @@\n same()\n-old()\n+new()", old_path="src/before.py",
    )
    index = FindingAnchorIndex(owned_diff_sections(renamed, [path], unified=True))
    assert index.locate(path, AnchorQuote(text="same()")).status == "AMBIGUOUS"
    assert index.locate(path, AnchorQuote(text="new()", side="OLD")).status == "UNMATCHED"
    assert index.locate(path, AnchorQuote(text="same()\r\nnew()", side="NEW")).location.startLine == 21
    assert index.locate(path, AnchorQuote(text="old()")).location.filePath == "src/before.py"
    assert index.locate("missing.py", AnchorQuote(text="old()")).reasonCode == "MISSING_DIFF"
    truncated = with_diff_section_header(path, "@@ -1,2 +1,2 @@\n before\n+after")
    assert FindingAnchorIndex(owned_diff_sections(truncated, [path], unified=True)).locate(
        path, AnchorQuote(text="after"),
    ).reasonCode == "MISSING_DIFF"
    hunkless = with_diff_section_header(path, "+after")
    assert FindingAnchorIndex(owned_diff_sections(hunkless, [path], unified=True)).locate(
        path, AnchorQuote(text="after"),
    ).reasonCode == "MISSING_DIFF"
    validate_wait_limit(path, index)
    for protocol in ("chat", "responses"):
        run_fixture(protocol, fixture_case([path], 5), use_candidates=True, delayed=True)
        run_fixture(protocol, fixture_case([path, "src/other.py"], 55), use_candidates=True)
        run_fixture(protocol, fixture_case([path], 5), use_candidates=False)

    large = fixture_case([path], 6_000)
    timings: dict[str, Any] = {}
    for name, use_candidates in (("direct", False), ("async", True)):
        elapsed, waits = [], []
        for _ in range(5):
            _, progress, duration = run_fixture("chat", large, use_candidates=use_candidates)
            elapsed.append(duration)
            waits.extend(row["anchorProgress"]["durationMs"] for row in progress.values())
        timings[name] = {
            "taskP50Ms": round(sorted(elapsed)[len(elapsed) // 2], 1), "taskP95Ms": round(max(elapsed), 1),
            "waitP50Ms": sorted(waits)[len(waits) // 2], "waitP95Ms": max(waits),
        }
    return {"status": "PASS", "protocols": ["chat", "responses"], "syntheticLargeDiff": timings}


def validate_wait_limit(path: str, index: FindingAnchorIndex) -> None:
    cancelled, started, release = Event(), Event(), Event()
    pool = AnchorPool(cancelled)
    candidates = ReviewCandidates({path}, index, pool, lambda: None)
    finding = GroupedSyntheticTransport._finding(path)
    identity = finding_identity(finding)

    locate = index.locate

    def held_lookup(file_path: str, quote: AnchorQuote):
        started.set()
        release.wait(2)
        return locate(file_path, quote)

    try:
        with patch.object(index, "locate", side_effect=held_lookup):
            reference = candidates.submit_candidate({
                "filePath": path, "title": "Fixture", "body": "Fixture", "anchorQuote": {"text": "old()"},
            })
            assert started.wait(1)
            candidates.validate_submission({
                "summary": "Fixture", "overallLevel": "HIGH", "findings": [{**finding, **reference}],
            }, [path])
            start = perf_counter()
            assert candidates.settle({identity: finding}, remaining=float("inf"))[identity].reasonCode == "TIME_BUDGET"
            assert perf_counter() - start < ANCHOR_WAIT_SECONDS + 0.25
        another_pass = ReviewCandidates({path}, index, pool, lambda: None)
        another_pass.validate_submission({
            "summary": "Fixture", "overallLevel": "HIGH", "findings": [{**finding, **reference}],
        }, [path])
        assert another_pass.settle({identity: finding}, remaining=1)[identity].reasonCode == "INVALID_CANDIDATE"
        another_pass.validate_submission({
            "summary": "Fixture", "overallLevel": "HIGH",
            "findings": [{**finding, **reference, "anchorQuote": {"text": "old()"}}],
        }, [path])
        assert another_pass.settle({identity: finding}, remaining=1)[identity].status == "MATCHED"
    finally:
        release.set()
        pool.close()


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
