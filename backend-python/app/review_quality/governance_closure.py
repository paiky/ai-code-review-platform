import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.json_utils import read_json, utc_now
from app.evaluation.models import EvaluationRun, EvaluationRunItem
from app.release_metadata import normalize_release_sha
from app.review_quality.governance_models import GovernanceControl, GovernanceRun
from app.review_quality.governance_queue import add_event
from app.review_quality.governance_service import lock_issue, require_governance
from app.review_quality.monitoring import get_monitoring_report
from app.review_quality.monitoring_models import MonitoringIssue
from app.review_quality.monitoring_schemas import MonitoringReportResponse


MIN_OBSERVATIONS = 10
METRIC_KEY = "CONTEXT_OVER_TARGET"


def _cohort(report: MonitoringReportResponse) -> tuple[str, int, int] | None:
    snapshot = report.snapshot
    if not snapshot or snapshot.truncated:
        return None
    release = next((item for item in snapshot.releaseCohorts if item.engine == "STANDARD"), None)
    metric = next((item for item in snapshot.metrics if item.engine == "STANDARD"
                   and item.group == "STANDARD" and item.key == METRIC_KEY), None)
    if not release or release.status != "KNOWN" or not metric or not (
        metric.eligibleCount == metric.observedCount == release.eligibleCount >= MIN_OBSERVATIONS
        and metric.unknownCount == 0 and type(metric.value) is int
    ):
        return None
    return release.releases[0].backendRelease, metric.value, metric.observedCount


def _paired_replay(db: Session, issue: MonitoringIssue, before: str, after: str, summary: dict) -> bool:
    run = db.scalar(select(EvaluationRun).where(
        EvaluationRun.id == issue.evaluation_run_id, EvaluationRun.project_id == issue.project_id,
        EvaluationRun.run_type == "REVIEW_REPLAY",
    ))
    if run is None:
        return False
    items = db.scalars(select(EvaluationRunItem).where(
        EvaluationRunItem.run_id == run.id, EvaluationRunItem.project_id == issue.project_id,
        EvaluationRunItem.status == "COMPLETED",
    ))
    for item in items:
        baseline = read_json(item.baseline_summary_json, {})
        candidate = read_json(item.candidate_summary_json, {})
        if not isinstance(baseline, dict) or not isinstance(candidate, dict):
            continue
        if (
            baseline.get("kind") == candidate.get("kind") == "STANDARD_CONTEXT"
            and baseline.get("fixtureSha256") == candidate.get("fixtureSha256") == summary["fixtureSha256"]
            and baseline.get("build") == before and candidate.get("build") == after
            and baseline.get("passed") is False and candidate.get("passed") is True
            and type(baseline.get("contextPromptChars")) is int
            and type(baseline.get("targetContextChars")) is int
            and baseline["contextPromptChars"] > baseline["targetContextChars"] == summary["targetContextChars"]
            and candidate.get("contextPromptChars") == summary["contextPromptChars"]
            and candidate.get("retainedExpectedEvidenceCount") == summary["retainedExpectedEvidenceCount"]
        ):
            return True
    return False


def close_verified_issues(db: Session, report: MonitoringReportResponse) -> list[int]:
    if os.getenv("REVIEW_QUALITY_GOVERNANCE_AUTO_CLOSE", "").lower() != "true":
        return []
    require_governance(db)
    observed = _cohort(report)
    if observed is None or observed[1] != 0:
        return []
    candidate_build = observed[0]
    closed = []
    candidates = list(db.scalars(select(MonitoringIssue.id).where(
        MonitoringIssue.project_id == report.projectId,
        MonitoringIssue.engine == "STANDARD", MonitoringIssue.issue_type == "CONTEXT_BUDGET",
        MonitoringIssue.diagnostic_type == "OVER_TARGET", MonitoringIssue.status == "VERIFYING",
        MonitoringIssue.evaluation_run_id.is_not(None),
    )))
    db.rollback()
    for issue_id in candidates:
        issue = lock_issue(db, report.projectId, issue_id)
        control = db.get(GovernanceControl, issue.id, with_for_update=True)
        if issue.status != "VERIFYING" or (control and (control.paused or control.conclusion)):
            db.rollback()
            continue
        run = db.scalar(select(GovernanceRun).where(
            GovernanceRun.project_id == report.projectId, GovernanceRun.issue_id == issue.id,
        ).order_by(GovernanceRun.id.desc()).limit(1).with_for_update())
        replay_result = run.result_json.get("replay", {}) if run and run.status == "SUCCEEDED" else {}
        if (not replay_result.get("passed") or normalize_release_sha(replay_result.get("build")) != candidate_build
                or run.result_json.get("assessment", {}).get("action") != "OBSERVE"):
            db.rollback()
            continue
        baseline = get_monitoring_report(db, report.projectId, run.report_id)
        prior = _cohort(baseline)
        if not (
            prior and prior[0] != candidate_build and prior[1] > 0
            and baseline.ruleVersion == report.ruleVersion
            and baseline.endAt <= report.startAt
            and baseline.endAt - baseline.startAt == report.endAt - report.startAt
            and issue.last_seen_at < baseline.endAt.replace(tzinfo=None)
            and _paired_replay(db, issue, prior[0], candidate_build, replay_result)
        ):
            db.rollback()
            continue
        issue.status = "CLOSED"
        issue.closed_at = utc_now()
        issue.version += 1
        add_event(db, run, "AUTO_CLOSED", {
            "baselineReportId": baseline.id, "observationReportId": report.id,
            "evaluationRunId": issue.evaluation_run_id, "observedCount": observed[2],
        })
        closed.append(issue.id)
        db.commit()
    return closed
