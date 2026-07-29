from __future__ import annotations

from math import ceil
from typing import Any

from app.agent_review_spike.schema import normalize_relative_path


NO_REPORT_VERDICTS = {"FALSE_POSITIVE", "DUPLICATE"}
REPORT_VERDICTS = {
    "TRUE_POSITIVE",
    "LEVEL_TOO_HIGH",
    "LEVEL_TOO_LOW",
    "MISSING_FINDING",
}


def expected_outcome(case: dict[str, Any]) -> str:
    explicit = str(case.get("expectation") or "").strip().upper()
    if explicit in {"REPORT", "NO_REPORT"}:
        return explicit
    verdict = str(case.get("verdict") or "").strip().upper()
    if verdict in NO_REPORT_VERDICTS:
        return "NO_REPORT"
    if verdict in REPORT_VERDICTS:
        return "REPORT"
    raise ValueError("expectation is required for CONTEXT_MISSING or UNKNOWN cases")


def target_is_reported(card: dict[str, Any], target: dict[str, Any]) -> bool:
    target_path = normalize_relative_path(target.get("filePath"), "targetFinding.filePath")
    target_start = int(target.get("startLine") or 1)
    target_end = int(target.get("endLine") or target_start)
    category = str(target.get("category") or "").strip().upper()
    keywords = [str(item).casefold() for item in target.get("titleKeywords") or [] if str(item)]
    tolerance = max(min(int(target.get("lineTolerance") or 5), 50), 0)
    for finding in card.get("findings") or []:
        if normalize_relative_path(finding.get("filePath")) != target_path:
            continue
        finding_start = int(finding.get("startLine") or 1)
        finding_end = int(finding.get("endLine") or finding_start)
        if finding_end + tolerance < target_start or finding_start - tolerance > target_end:
            continue
        if category and str(finding.get("category") or "").upper() != category:
            continue
        title = str(finding.get("title") or "").casefold()
        if keywords and not all(keyword in title for keyword in keywords):
            continue
        return True
    return False


def execution_summary(
    case: dict[str, Any],
    *,
    status: str,
    duration_ms: int,
    card: dict[str, Any] | None = None,
    error_code: str | None = None,
    audit: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "durationMs": max(int(duration_ms), 0),
        "errorCode": error_code,
        "targetReported": False,
        "findingCount": 0,
        "contextMissingCount": 0,
    }
    if card is not None:
        findings = card.get("findings") or []
        target = case.get("targetFinding")
        result.update(
            {
                # targetFinding 只属于离线准确率样本；真实生产任务没有预设目标问题。
                "targetReported": (
                    target_is_reported(card, target) if isinstance(target, dict) else False
                ),
                "findingCount": len(findings),
                "contextMissingCount": sum(
                    1
                    for finding in findings
                    if finding.get("contextStatus") in {"PARTIAL", "INSUFFICIENT"}
                ),
                "overallLevel": card.get("overallLevel"),
            }
        )
    if audit:
        result["toolCallCount"] = int(audit.get("toolCallCount") or 0)
        result["sourceBytesReturned"] = int(audit.get("sourceBytesReturned") or 0)
        result["diffBytesReturned"] = int(audit.get("diffBytesReturned") or 0)
        result["blockedAccessCount"] = int(audit.get("blockedAccessCount") or 0)
        result["securityViolationCount"] = int(audit.get("blockedAccessCount") or 0)
        result["topPathSummaries"] = list(audit.get("topPathSummaries") or [])[:20]
    if session:
        result["sessionId"] = session.get("sessionId")
        result["numTurns"] = session.get("numTurns")
    return result


def build_report_metrics(
    cases: list[dict[str, Any]],
    case_results: list[dict[str, Any]],
    attestations: dict[str, Any],
) -> dict[str, Any]:
    baseline = _aggregate(cases, case_results, "baseline")
    candidate = _aggregate(cases, case_results, "candidate")
    baseline_context_fp = baseline["contextFalsePositiveCount"]
    context_reduction = (
        (baseline_context_fp - candidate["contextFalsePositiveCount"]) / baseline_context_fp
        if baseline_context_fp > 0
        else None
    )
    baseline_recall = baseline["recall"]
    candidate_recall = candidate["recall"]
    recall_drop = (
        baseline_recall - candidate_recall
        if baseline_recall is not None and candidate_recall is not None
        else None
    )
    sample_count = len(cases)
    candidate_error_rate = candidate["errorCount"] / sample_count if sample_count else 1.0
    gates = {
        "minimumSampleCount": sample_count >= 30,
        "hasContextFalsePositiveBaseline": baseline_context_fp > 0,
        "contextFalsePositiveReductionAtLeast20Percent": context_reduction is not None
        and context_reduction >= 0.2,
        "overallFalsePositiveNotIncreased": candidate["falsePositiveCount"]
        <= baseline["falsePositiveCount"],
        "recallDropWithin5Points": recall_drop is not None and recall_drop <= 0.05,
        "candidateErrorRateWithin5Percent": candidate_error_rate <= 0.05,
        "candidateP95Within10Minutes": candidate["p95DurationMs"] is not None
        and candidate["p95DurationMs"] <= 600_000,
        "readOnlyMountAttested": bool(attestations.get("readOnlyMount")),
        "deepseekOnlyEgressAttested": bool(attestations.get("deepseekOnlyEgress")),
        "securityViolationCountZero": candidate["securityViolationCount"] == 0,
    }
    if sample_count < 30:
        status = "INSUFFICIENT_SAMPLE"
    else:
        status = "PASS" if all(gates.values()) else "FAIL"
    return {
        "status": status,
        "sampleCount": sample_count,
        "baseline": baseline,
        "candidate": candidate,
        "delta": {
            "contextFalsePositiveRelativeReduction": context_reduction,
            "recallDrop": recall_drop,
            "candidateErrorRate": candidate_error_rate,
        },
        "gates": gates,
    }


def _aggregate(
    cases: list[dict[str, Any]], case_results: list[dict[str, Any]], side: str
) -> dict[str, Any]:
    by_id = {str(item["caseId"]): item for item in case_results}
    expected_report_count = 0
    true_positive_count = 0
    false_positive_count = 0
    context_false_positive_count = 0
    error_count = 0
    context_missing_count = 0
    blocked_access_count = 0
    security_violation_count = 0
    durations: list[int] = []
    for case in cases:
        execution = (by_id.get(str(case["id"])) or {}).get(side) or {}
        if execution.get("status") != "SUCCESS":
            error_count += 1
        else:
            durations.append(int(execution.get("durationMs") or 0))
        context_missing_count += int(execution.get("contextMissingCount") or 0)
        blocked_access_count += int(execution.get("blockedAccessCount") or 0)
        security_violation_count += int(execution.get("securityViolationCount") or 0)
        expectation = expected_outcome(case)
        reported = bool(execution.get("targetReported"))
        if expectation == "REPORT":
            expected_report_count += 1
            true_positive_count += int(reported)
        elif reported:
            false_positive_count += 1
            if bool(case.get("contextRelated")):
                context_false_positive_count += 1
    recall = (
        true_positive_count / expected_report_count if expected_report_count > 0 else None
    )
    return {
        "expectedReportCount": expected_report_count,
        "truePositiveCount": true_positive_count,
        "falsePositiveCount": false_positive_count,
        "contextFalsePositiveCount": context_false_positive_count,
        "recall": recall,
        "errorCount": error_count,
        "contextMissingCount": context_missing_count,
        "blockedAccessCount": blocked_access_count,
        "securityViolationCount": security_violation_count,
        "p95DurationMs": _percentile_95(durations),
    }


def _percentile_95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(ceil(len(ordered) * 0.95) - 1, 0)]
