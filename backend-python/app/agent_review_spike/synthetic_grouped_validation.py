"""Offline acceptance for the grouped Chat Completions execution path."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Lock
from typing import Any

from app.agent_review_spike.chat_completions_runner import OpenAIChatCompletionsAgentRunner
from app.agent_review_spike.diff import with_diff_section_header
from app.agent_review.schemas import GroupedReviewSettings
from app.agent_review_spike.grouped import run_grouped_review, validate_group_coverage
from app.agent_review_spike.synthetic_chat_completions_validation import _call, _response
from app.review_rules.catalog import built_in_catalog


_PATHS = [
    "db/OrderMapper.xml", "db/OrderDao.java", "web/OrderPage.tsx",
    *(f"service/{index}/dispatch.py" for index in range(7)),
]


class GroupedSyntheticTransport:
    def __init__(
        self, *, concurrent: bool = True, broken_grouping: bool = False, three_passes: bool = False,
    ) -> None:
        self.barrier = Barrier(8) if concurrent else None
        self.second_pass_barrier = Barrier(2) if concurrent else None
        self.broken_grouping = broken_grouping
        self.three_passes = three_passes
        self.lock = Lock()
        self.active = 0
        self.peak = 0
        self.initial_paths: list[tuple[str, ...]] = []
        self.second_passes: list[tuple[str, ...]] = []
        self.third_passes = 0
        self.fact_checks: dict[str, list[str]] = {}
        self.cross_group_read = False
        self.rejected_outside_finding = False

    def create(self, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        del timeout_seconds
        messages = payload["messages"]
        if "Partition the supplied changed files" in messages[0]["content"]:
            changes = json.loads(messages[1]["content"])
            assert [item["path"] for item in changes] == _PATHS
            assert all(set(item) == {"index", "path", "status", "additions", "deletions"} for item in changes)
            text = (
                "invalid grouping response" if self.broken_grouping else json.dumps(
                    [{"files": [0, 1]}, {"files": [1, 2, 999]}, *({"files": [i]} for i in range(3, 9))]
                )
            )
            return {"choices": [{"message": {"content": text}}], "usage": {"total_tokens": 2}}

        if messages[0]["content"].startswith("Check whether the supplied diff"):
            request = json.loads(messages[1]["content"])
            findings = request["findings"]
            path = findings[0]["filePath"]
            assert len(findings) == 1 and path in request["diff"]
            with self.lock:
                self.fact_checks.setdefault(path, []).append(findings[0]["title"])
            if path == _PATHS[3]:
                raise TimeoutError("Synthetic review timeout")
            verdict = {
                "findingId": findings[0]["findingId"], "verdict": "CONTRADICTED",
                "reason": "The patch contains the expected guard.",
                "evidence": {
                    "filePath": path, "side": "NEW", "startLine": 1,
                    "endLine": 99 if path == _PATHS[4] else 1,
                },
            }
            return {
                "choices": [{"message": {"content": json.dumps([verdict])}}],
                "usage": {"total_tokens": 1},
            }

        prompt = messages[1]["content"]
        paths = tuple(ast.literal_eval(prompt.split("Changed files: ", 1)[1].splitlines()[0]))
        if len(paths) == 2:
            assert "Rule mapper_dao_xml.md" in messages[0]["content"]
            assert "Rule java.md" in messages[0]["content"]
            assert "Rule ts_js_tsx_jsx.md" not in messages[0]["content"]
        if paths == (_PATHS[2],):
            assert "Rule ts_js_tsx_jsx.md" in messages[0]["content"]
        if "Findings already reported for this group" in prompt:
            assert len(messages) == 2 and len(paths) == 1
            assert self._finding(paths[0])["title"] in prompt
            carried = json.loads(prompt.split(
                "Findings already reported for this group (do not repeat them; look for omissions):\n", 1,
            )[1].splitlines()[0])
            assert all(item["filePath"] in paths for item in carried)
            assert self.fact_checks[paths[0]] == [item["title"] for item in carried]
            if len(carried) == 2:
                self.third_passes += 1
                return self._submit(paths[0], issues=False)
            with self.lock:
                self.second_passes.append(paths)
                wait_on_second_pass = len(self.second_passes) <= 2
            if wait_on_second_pass and self.second_pass_barrier is not None:
                self.second_pass_barrier.wait(timeout=8)
            if self.three_passes:
                finding = {**self._finding(paths[0]), "title": f"Additional finding for {paths[0]}"}
                return _response(1, [_call("submit", "submit_review", {
                    "summary": "Synthetic additional check", "overallLevel": "HIGH", "findings": [finding],
                })])
            return self._submit(paths[0])

        if len(messages) == 2:
            with self.lock:
                waits = len(self.initial_paths) < 8
                self.initial_paths.append(paths)
                self.active += 1
                self.peak = max(self.peak, self.active)
            if waits and self.barrier is not None:
                self.barrier.wait(timeout=8)
            with self.lock:
                self.active -= 1
            if paths == (_PATHS[2],) and not self.broken_grouping:
                return _response(1, [_call("diff", "read_diff_range", {
                    "path": _PATHS[0], "startLine": 1, "endLine": 4,
                })])
            return self._submit(paths[0], issues=paths[0].startswith("service/"))

        tool = json.loads(messages[-1]["content"])
        if messages[-1]["tool_call_id"] == "diff":
            self.cross_group_read = tool["path"] == _PATHS[0] and "fixed new" in tool["content"]
            return self._submit(_PATHS[0], call_id="outside")
        self.rejected_outside_finding = "PATH_OUTSIDE_CHANGED_FILES" in json.dumps(tool)
        return self._submit(paths[0], issues=False, call_id="repair")

    def _submit(self, path: str, *, issues: bool = True, call_id: str = "submit") -> dict[str, Any]:
        return _response(1, [_call(call_id, "submit_review", {
            "summary": "Synthetic grouped check",
            "overallLevel": "HIGH" if issues else "LOW",
            "findings": [self._finding(path)] if issues else [],
        })])

    @staticmethod
    def _finding(path: str) -> dict[str, Any]:
        return {
            "severity": "MAJOR", "category": "CORRECTNESS", "filePath": path,
            "startLine": 1, "endLine": 1, "title": f"Finding for {path}",
            "body": "Synthetic issue", "suggestion": "Inspect the synthetic change",
            "confidence": "HIGH", "contextStatus": "SUFFICIENT", "contextSummary": "Fixture",
            "evidence": ["fixed new"], "missingContext": [],
        }


def synthetic_case() -> dict[str, Any]:
    return {
        "id": "synthetic-grouped-review", "changedFiles": _PATHS,
        "groupRuleCatalogVersion": built_in_catalog().version,
        "groupBaseInstructions": "Synthetic acceptance",
        "diff": "\n".join(
            with_diff_section_header(path, "@@ -1 +1 @@\n-fixed old\n+fixed new")
            for path in _PATHS
        ),
    }



def validate() -> dict[str, Any]:
    case = synthetic_case()
    with TemporaryDirectory(prefix="agent-grouped-validation-") as name:
        worktree = Path(name)
        transport = GroupedSyntheticTransport()
        progress = []
        result = run_grouped_review(
            OpenAIChatCompletionsAgentRunner(transport), case, worktree, GroupedReviewSettings(),
            cancel_event=Event(), progress=progress.append,
        )
        assert result["status"] == "SUCCESS", result
        validate_group_coverage(result["groupCoverage"], _PATHS)
        assert len(result["groupCoverage"]) == 9
        assert transport.peak == 8 and len(transport.initial_paths) == 9
        assert progress[0]["groups"][8]["status"] == "QUEUED"
        assert transport.cross_group_read and transport.rejected_outside_finding
        assert len(transport.second_passes) == len(result["card"]["findings"]) == 7
        assert sum(map(len, transport.fact_checks.values())) == 7
        assert len(result["factCheckResults"]) == 7
        assert {item.get("reasonCode") for item in result["factCheckResults"]} == {
            None, "TIMEOUT", "INVALID_EVIDENCE",
        }

        sequential = GroupedSyntheticTransport(concurrent=False)
        serial = run_grouped_review(
            OpenAIChatCompletionsAgentRunner(sequential), case, worktree,
            GroupedReviewSettings(concurrency=1), cancel_event=Event(), progress=lambda value: None,
        )
        assert sequential.peak == 1 and serial["card"] == result["card"]
        assert serial["factCheckResults"] == result["factCheckResults"]
        assert serial["usage"]["total_tokens"] == result["usage"]["total_tokens"]

        broken = GroupedSyntheticTransport(concurrent=False, broken_grouping=True)
        fallback_progress = []
        fallback = run_grouped_review(
            OpenAIChatCompletionsAgentRunner(broken), case, worktree,
            GroupedReviewSettings(concurrency=1, maxPasses=1),
            cancel_event=Event(), progress=fallback_progress.append,
        )
        assert fallback["status"] == "SUCCESS"
        validate_group_coverage(fallback["groupCoverage"], _PATHS)
        assert fallback_progress[-1]["mode"] == "PER_FILE_FALLBACK"
        assert len(fallback["groupCoverage"]) == len(_PATHS) and not broken.second_passes

        high = GroupedSyntheticTransport(concurrent=False, three_passes=True)
        high_result = run_grouped_review(
            OpenAIChatCompletionsAgentRunner(high), case, worktree,
            GroupedReviewSettings(concurrency=1, maxPasses=3),
            cancel_event=Event(), progress=lambda value: None,
        )
        assert high_result["status"] == "SUCCESS" and high.third_passes == 7
        assert {item["passNo"] for item in high_result["factCheckResults"]} == {1, 2}

        limited = GroupedSyntheticTransport(concurrent=False)
        limited_result = run_grouped_review(
            OpenAIChatCompletionsAgentRunner(limited), case, worktree,
            GroupedReviewSettings(concurrency=1, maxTokens=2),
            cancel_event=Event(), progress=lambda value: None,
        )
        assert limited_result["errorCode"] == "AGENT_GROUP_TOKEN_BUDGET" and not limited.initial_paths

    return {
        "groups": len(result["groupCoverage"]), "peakConcurrentRequests": transport.peak,
        "maxPasses": progress[-1]["maxPasses"], "secondPasses": len(transport.second_passes),
        "highEffortThirdPasses": high.third_passes, "tokenBudgetStopsDispatch": not limited.initial_paths,
        "sameSerialResult": serial["card"] == result["card"],
        "factChecks": len(result["factCheckResults"]),
        "factCheckFailuresRetained": sum(item["status"] == "FAILED" for item in result["factCheckResults"]),
        "crossGroupDiffReadable": transport.cross_group_read,
        "crossGroupFindingRejected": transport.rejected_outside_finding,
        "malformedGroupingFallback": fallback_progress[-1]["mode"],
    }


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2))
