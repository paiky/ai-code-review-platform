from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityFindingRefinement
from app.code_quality.refinement_repository import ensure_finding_refinement_schema
from app.core.json_utils import read_json
from app.deterministic_checks.models import DeterministicCheckRun
from app.deterministic_checks.repository import ensure_deterministic_check_schema
from app.evaluation.models import EvaluationCase, EvaluationRunItem
from app.evaluation.repository import ensure_evaluation_case_schema, ensure_evaluation_run_schema
from app.evaluation.service import VERDICTS
from app.project_integration.models import Project


_COUNT_FIELDS = (
    "findingCount",
    "falsePositiveCount",
    "contextMissingCount",
    "missingFindingCount",
    "levelTooHighCount",
    "levelTooLowCount",
    "duplicateFindingCount",
)
_VERDICT_METRIC_MAP = {
    "FALSE_POSITIVE": "falsePositiveCount",
    "CONTEXT_MISSING": "contextMissingCount",
    "LEVEL_TOO_HIGH": "levelTooHighCount",
    "LEVEL_TOO_LOW": "levelTooLowCount",
    "DUPLICATE": "duplicateFindingCount",
    "MISSING_FINDING": "missingFindingCount",
}


def get_review_quality_dashboard(
    db: Session,
    *,
    project_id: int | None,
    provider: str | None,
    profile: str | None,
    risk_type: str | None,
    verdict: str | None,
) -> dict[str, Any]:
    ensure_evaluation_case_schema(db)
    ensure_evaluation_run_schema(db)
    normalized = {
        "projectId": project_id,
        "provider": _clean_filter(provider),
        "profile": _clean_filter(profile),
        "riskType": _clean_filter(risk_type),
        "verdict": _normalize_verdict(verdict),
    }
    cases = _filtered_cases(db, normalized)
    project_map = _project_map(db, {case.project_id for case in cases})
    summary = _quality_summary(cases)
    return {
        "filters": normalized,
        "summary": summary,
        "verdictDistribution": _verdict_distribution(summary["verdictCounts"]),
        "dimensions": {
            "projects": _dimension_rows(cases, "project", project_map),
            "providers": _dimension_rows(cases, "provider", project_map),
            "profiles": _dimension_rows(cases, "profile", project_map),
            "riskTypes": _dimension_rows(cases, "riskType", project_map),
        },
        "replaySummary": _replay_summary(db, normalized),
        "refinementSummary": _refinement_summary(db, cases, normalized),
        "deterministicCheckSummary": _deterministic_check_summary(db, cases, normalized),
    }


def _filtered_cases(db: Session, filters: dict[str, Any]) -> list[EvaluationCase]:
    stmt = select(EvaluationCase)
    if filters["projectId"] is not None:
        stmt = stmt.where(EvaluationCase.project_id == filters["projectId"])
    if filters["provider"]:
        stmt = stmt.where(EvaluationCase.provider == filters["provider"])
    if filters["profile"]:
        stmt = stmt.where(EvaluationCase.profile == filters["profile"])
    if filters["riskType"]:
        stmt = stmt.where(EvaluationCase.risk_type == filters["riskType"])
    if filters["verdict"]:
        stmt = stmt.where(EvaluationCase.verdict == filters["verdict"])
    return list(db.scalars(stmt.order_by(EvaluationCase.created_at.desc(), EvaluationCase.id.desc())).all())


def _quality_summary(cases: list[EvaluationCase]) -> dict[str, Any]:
    verdict_counts = {verdict: 0 for verdict in sorted(VERDICTS)}
    for case in cases:
        verdict_counts[case.verdict or "UNKNOWN"] = verdict_counts.get(case.verdict or "UNKNOWN", 0) + 1
    sample_count = len(cases)
    result = {
        "sampleCount": sample_count,
        "verdictCounts": verdict_counts,
    }
    for verdict, metric in _VERDICT_METRIC_MAP.items():
        result[metric] = int(verdict_counts.get(verdict, 0))
    result["falsePositiveRate"] = _rate(result["falsePositiveCount"], sample_count)
    result["contextMissingRate"] = _rate(result["contextMissingCount"], sample_count)
    return result


def _verdict_distribution(verdict_counts: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "verdict": verdict,
            "count": int(verdict_counts.get(verdict, 0)),
        }
        for verdict in sorted(VERDICTS)
    ]


def _dimension_rows(
    cases: list[EvaluationCase],
    dimension: str,
    project_map: dict[int, Project],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[EvaluationCase]] = defaultdict(list)
    for case in cases:
        key = _dimension_key(case, dimension)
        grouped[key].append(case)
    rows = []
    for key, records in grouped.items():
        row = {
            "key": key,
            "label": _dimension_label(key, records, dimension, project_map),
            **_quality_summary(records),
        }
        if dimension == "project" and key != "UNSPECIFIED":
            row["projectId"] = int(key)
        rows.append(row)
    rows.sort(key=lambda item: (-int(item["sampleCount"]), str(item["label"])))
    return rows[:20]


def _dimension_key(case: EvaluationCase, dimension: str) -> str:
    if dimension == "project":
        return str(case.project_id) if case.project_id is not None else "UNSPECIFIED"
    if dimension == "provider":
        return case.provider or "UNSPECIFIED"
    if dimension == "profile":
        return case.profile or "UNSPECIFIED"
    if dimension == "riskType":
        return case.risk_type or "UNSPECIFIED"
    return "UNSPECIFIED"


def _dimension_label(
    key: str,
    records: list[EvaluationCase],
    dimension: str,
    project_map: dict[int, Project],
) -> str:
    if dimension != "project" or key == "UNSPECIFIED":
        return key
    project = project_map.get(records[0].project_id)
    return project.name if project is not None else key


def _replay_summary(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    stmt = select(EvaluationRunItem)
    stmt = _apply_item_filters(stmt, filters)
    items = list(db.scalars(stmt).all())
    status_counts = Counter(item.status or "UNKNOWN" for item in items)
    duration_values = [int(item.duration_ms) for item in items if item.duration_ms is not None]
    return {
        "itemCount": len(items),
        "statusCounts": dict(status_counts),
        "completedCount": int(status_counts.get("COMPLETED", 0)),
        "failedCount": int(status_counts.get("FAILED", 0)),
        "durationMsTotal": sum(duration_values),
        "durationMsAvg": round(sum(duration_values) / len(duration_values), 4) if duration_values else 0,
        "baselineTotals": _summary_totals(items, "baseline_summary_json"),
        "candidateTotals": _summary_totals(items, "candidate_summary_json"),
        "resultTotals": _summary_totals(items, "result_summary_json"),
    }


def _apply_item_filters(stmt: Any, filters: dict[str, Any]) -> Any:
    if filters["projectId"] is not None:
        stmt = stmt.where(EvaluationRunItem.project_id == filters["projectId"])
    if filters["provider"]:
        stmt = stmt.where(EvaluationRunItem.provider == filters["provider"])
    if filters["profile"]:
        stmt = stmt.where(EvaluationRunItem.profile == filters["profile"])
    if filters["riskType"]:
        stmt = stmt.where(EvaluationRunItem.risk_type == filters["riskType"])
    if filters["verdict"]:
        stmt = stmt.where(EvaluationRunItem.verdict == filters["verdict"])
    return stmt


def _summary_totals(items: list[EvaluationRunItem], field_name: str) -> dict[str, int]:
    totals = {field: 0 for field in _COUNT_FIELDS}
    for item in items:
        value = read_json(getattr(item, field_name), {})
        if not isinstance(value, dict):
            continue
        for field in _COUNT_FIELDS:
            raw = value.get(field)
            if isinstance(raw, (int, float)):
                totals[field] += int(raw)
    return totals


def _refinement_summary(
    db: Session,
    cases: list[EvaluationCase],
    filters: dict[str, Any],
) -> dict[str, Any]:
    ensure_finding_refinement_schema(db)
    task_ids = {int(case.task_id) for case in cases if case.task_id is not None}
    project_ids = _project_scope(cases, filters)
    stmt = select(CodeQualityFindingRefinement)
    scope_note = "Refinements are linked by filtered evaluation case task ids."
    if task_ids:
        stmt = stmt.where(CodeQualityFindingRefinement.task_id.in_(task_ids))
    elif project_ids:
        stmt = stmt.where(CodeQualityFindingRefinement.project_id.in_(project_ids))
        scope_note = "No filtered evaluation case task ids were available; refinements are summarized by project scope."
    else:
        return {
            "recordCount": 0,
            "statusCounts": {},
            "completedCount": 0,
            "failedCount": 0,
            "failureReasons": [],
            "scopeNote": "No matching evaluation case or project scope is available.",
        }
    records = list(db.scalars(stmt).all())
    status_counts = Counter(record.status or "UNKNOWN" for record in records)
    return {
        "recordCount": len(records),
        "statusCounts": dict(status_counts),
        "completedCount": int(status_counts.get("COMPLETED", 0)),
        "failedCount": int(status_counts.get("FAILED", 0)),
        "failureReasons": _top_counts([_safe_text(record.failure_reason) for record in records if record.failure_reason]),
        "scopeNote": scope_note,
    }


def _deterministic_check_summary(
    db: Session,
    cases: list[EvaluationCase],
    filters: dict[str, Any],
) -> dict[str, Any]:
    ensure_deterministic_check_schema(db)
    project_ids = _project_scope(cases, filters)
    if not project_ids:
        return {
            "runCount": 0,
            "statusCounts": {},
            "findingCount": 0,
            "ruleTypeCounts": {},
            "scopeNote": "No matching project scope is available for deterministic checks.",
        }
    records = list(
        db.scalars(select(DeterministicCheckRun).where(DeterministicCheckRun.project_id.in_(project_ids))).all()
    )
    status_counts = Counter(record.status or "UNKNOWN" for record in records)
    rule_counts: Counter[str] = Counter()
    finding_count = 0
    for record in records:
        summary = read_json(record.result_summary_json, {})
        if not isinstance(summary, dict):
            continue
        finding_count += _to_int(summary.get("findingCount"))
        raw_rule_counts = summary.get("ruleTypeCounts")
        if isinstance(raw_rule_counts, dict):
            for key, value in raw_rule_counts.items():
                rule_counts[str(key)] += _to_int(value)
    scope_note = "Deterministic checks are project-scoped auxiliary diagnostics."
    if filters["provider"] or filters["profile"] or filters["riskType"] or filters["verdict"]:
        scope_note += " Provider/profile/riskType/verdict filters cannot be applied directly to deterministic check runs."
    return {
        "runCount": len(records),
        "statusCounts": dict(status_counts),
        "findingCount": finding_count,
        "ruleTypeCounts": dict(rule_counts),
        "scopeNote": scope_note,
    }


def _project_scope(cases: list[EvaluationCase], filters: dict[str, Any]) -> set[int]:
    if filters["projectId"] is not None:
        return {int(filters["projectId"])}
    return {int(case.project_id) for case in cases if case.project_id is not None}


def _project_map(db: Session, project_ids: set[int]) -> dict[int, Project]:
    if not project_ids:
        return {}
    records = db.scalars(select(Project).where(Project.id.in_(project_ids))).all()
    return {int(project.id): project for project in records}


def _top_counts(values: list[str]) -> list[dict[str, Any]]:
    counts = Counter(value for value in values if value)
    return [
        {"reason": key, "count": int(count)}
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0
    return round(count / total, 4)


def _clean_filter(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_verdict(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    return text if text in VERDICTS else text


def _to_int(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_text(value: Any) -> str:
    text = str(value or "").strip()
    for marker in ("Authorization", "apiKey", "api_key", "token", "secret", "password", "x-api-key"):
        lower = text.lower()
        index = lower.find(marker.lower())
        if index >= 0:
            text = text[: index + len(marker)] + ": ****"
    text = text.replace("\\", "/")
    if ":/" in text:
        text = "[local-path]"
    return text[:240]
