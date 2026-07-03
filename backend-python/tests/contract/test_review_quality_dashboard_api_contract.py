from __future__ import annotations

from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityFindingRefinement
from app.deterministic_checks.models import DeterministicCheckRun
from app.evaluation.models import EvaluationCase, EvaluationRunItem
from app.project_integration.models import Project
from app.review_quality_acceptance.models import ReviewQualityAcceptanceGate


def test_review_quality_dashboard_empty_state_is_explainable(client: TestClient) -> None:
    response = client.get("/api/review-quality/dashboard")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["sampleCount"] == 0
    assert data["summary"]["falsePositiveRate"] == 0
    assert data["summary"]["contextMissingRate"] == 0
    assert data["verdictDistribution"]
    assert all(item["count"] == 0 for item in data["verdictDistribution"])
    assert data["dimensions"]["projects"] == []
    assert data["replaySummary"]["itemCount"] == 0
    assert data["refinementSummary"]["recordCount"] == 0
    assert data["deterministicCheckSummary"]["runCount"] == 0
    assert data["acceptanceGateSummary"]["recordCount"] == 0


def test_review_quality_dashboard_aggregates_cases_and_dimensions(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_quality_dashboard_data(db_session)

    response = client.get("/api/review-quality/dashboard?projectId=9101&provider=DEEPSEEK&profile=backend-default-ai-review")

    assert response.status_code == 200
    data = response.json()["data"]
    summary = data["summary"]
    assert summary["sampleCount"] == 6
    assert summary["falsePositiveCount"] == 1
    assert summary["contextMissingCount"] == 1
    assert summary["levelTooHighCount"] == 1
    assert summary["levelTooLowCount"] == 1
    assert summary["duplicateFindingCount"] == 1
    assert summary["missingFindingCount"] == 1
    assert summary["falsePositiveRate"] == 0.1667
    assert summary["contextMissingRate"] == 0.1667

    verdict_counts = {item["verdict"]: item["count"] for item in data["verdictDistribution"]}
    assert verdict_counts["FALSE_POSITIVE"] == 1
    assert verdict_counts["MISSING_FINDING"] == 1

    project_rows = data["dimensions"]["projects"]
    assert project_rows[0]["projectId"] == 9101
    assert project_rows[0]["label"] == "quality-demo-service"
    assert project_rows[0]["sampleCount"] == 6

    risk_rows = {row["key"]: row for row in data["dimensions"]["riskTypes"]}
    assert risk_rows["SECURITY"]["sampleCount"] == 3
    assert risk_rows["SECURITY"]["falsePositiveCount"] == 1
    assert risk_rows["TRANSACTION"]["contextMissingCount"] == 1
    assert data["acceptanceGateSummary"]["recordCount"] == 1
    assert data["acceptanceGateSummary"]["latestStatus"] == "PASSED"


def test_review_quality_dashboard_filters_by_risk_type_and_verdict(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_quality_dashboard_data(db_session)

    response = client.get(
        "/api/review-quality/dashboard",
        params={
            "projectId": 9101,
            "provider": "DEEPSEEK",
            "profile": "backend-default-ai-review",
            "riskType": "SECURITY",
            "verdict": "FALSE_POSITIVE",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["sampleCount"] == 1
    assert data["summary"]["falsePositiveCount"] == 1
    assert data["summary"]["falsePositiveRate"] == 1
    assert data["summary"]["contextMissingCount"] == 0
    assert data["dimensions"]["riskTypes"][0]["key"] == "SECURITY"
    assert data["replaySummary"]["itemCount"] == 1
    assert data["replaySummary"]["baselineTotals"]["falsePositiveCount"] == 1
    assert data["replaySummary"]["candidateTotals"]["falsePositiveCount"] == 0
    assert data["acceptanceGateSummary"]["recordCount"] == 1
    assert data["acceptanceGateSummary"]["statusCounts"]["PASSED"] == 1


def test_review_quality_dashboard_auxiliary_summaries_are_safe(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_quality_dashboard_data(db_session)

    response = client.get("/api/review-quality/dashboard?projectId=9101&provider=DEEPSEEK")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["refinementSummary"]["recordCount"] == 2
    assert data["refinementSummary"]["failedCount"] == 1
    assert data["deterministicCheckSummary"]["runCount"] == 1
    assert data["deterministicCheckSummary"]["findingCount"] == 2
    assert data["deterministicCheckSummary"]["ruleTypeCounts"]["API_TOKEN_ASSIGNMENT"] == 2
    assert "Provider/profile/riskType/verdict filters cannot be applied directly" in data["deterministicCheckSummary"]["scopeNote"]
    assert data["acceptanceGateSummary"]["recordCount"] == 1
    assert "manual governance records" in data["acceptanceGateSummary"]["scopeNote"]

    payload = json.dumps(data, ensure_ascii=False)
    assert "super-secret-token" not in payload
    assert "Authorization: Bearer" not in payload
    assert r"D:\projects\private" not in payload
    assert "line with source code" not in payload
    assert "provider raw output" not in payload


def _seed_quality_dashboard_data(db_session: Session) -> None:
    now = datetime.now()
    db_session.add_all(
        [
            Project(
                id=9101,
                name="quality-demo-service",
                git_provider="GITLAB",
                git_project_id="quality-9101",
                repository_url="https://gitlab.example.com/demo/quality",
                default_template_code="backend-default",
                status="ENABLED",
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=9102,
                name="other-quality-service",
                git_provider="GITLAB",
                git_project_id="quality-9102",
                repository_url="https://gitlab.example.com/demo/quality-other",
                default_template_code="backend-default",
                status="ENABLED",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    cases = [
        _case(9111, 9101, 9201, "SECURITY", "FALSE_POSITIVE"),
        _case(9112, 9101, 9202, "TRANSACTION", "CONTEXT_MISSING"),
        _case(9113, 9101, 9203, "SECURITY", "LEVEL_TOO_HIGH"),
        _case(9114, 9101, 9204, "TRANSACTION", "LEVEL_TOO_LOW"),
        _case(9115, 9101, 9205, "MAINTAINABILITY", "DUPLICATE"),
        _case(9116, 9101, None, "SECURITY", "MISSING_FINDING", source="MANUAL"),
        _case(9117, 9102, 9211, "SECURITY", "FALSE_POSITIVE", provider="OPENAI"),
    ]
    db_session.add_all(cases)
    db_session.add_all(
        [
            EvaluationRunItem(
                id=9301,
                run_id=9401,
                case_id=9111,
                item_index=0,
                task_id=9201,
                review_key="deepseek-main",
                fingerprint="fp-9111",
                project_id=9101,
                provider="DEEPSEEK",
                profile="backend-default-ai-review",
                risk_type="SECURITY",
                severity="MAJOR",
                context_status="PARTIAL",
                verdict="FALSE_POSITIVE",
                status="COMPLETED",
                duration_ms=100,
                baseline_summary_json='{"findingCount":2,"falsePositiveCount":1,"contextMissingCount":1}',
                candidate_summary_json='{"findingCount":1,"falsePositiveCount":0,"contextMissingCount":0}',
                result_summary_json='{"matchedVerdict":true,"falsePositiveCount":1}',
                created_at=now,
                updated_at=now,
            ),
            EvaluationRunItem(
                id=9302,
                run_id=9401,
                case_id=9112,
                item_index=1,
                task_id=9202,
                review_key="deepseek-main",
                fingerprint="fp-9112",
                project_id=9101,
                provider="DEEPSEEK",
                profile="backend-default-ai-review",
                risk_type="TRANSACTION",
                severity="MAJOR",
                context_status="INSUFFICIENT",
                verdict="CONTEXT_MISSING",
                status="FAILED",
                duration_ms=200,
                error_message="manual replay failed",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.add_all(
        [
            CodeQualityFindingRefinement(
                id=9501,
                task_id=9201,
                review_key="deepseek-main",
                finding_index=0,
                fingerprint="fp-9111",
                finding_id="finding-1",
                project_id=9101,
                status="COMPLETED",
                trigger_reason="HIGH_IMPACT_CONTEXT_INSUFFICIENT",
                trigger_conditions_json="{}",
                evidence_summary_json='{"sourceSnippet":"line with source code"}',
                missing_context_json="[]",
                created_at=now,
                updated_at=now,
            ),
            CodeQualityFindingRefinement(
                id=9502,
                task_id=9202,
                review_key="deepseek-main",
                finding_index=0,
                fingerprint="fp-9112",
                finding_id="finding-2",
                project_id=9101,
                status="FAILED",
                trigger_reason="HIGH_IMPACT_CONTEXT_INSUFFICIENT",
                trigger_conditions_json="{}",
                failure_reason=r"Authorization: Bearer super-secret-token D:\projects\private\repo",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.add(
        DeterministicCheckRun(
            id=9601,
            task_id=9201,
            project_id=9101,
            check_type="SECRET_SCAN",
            status="COMPLETED",
            config_snapshot_json='{"rulesetVersion":"secret-scan-mvp-v1"}',
            result_summary_json='{"findingCount":2,"ruleTypeCounts":{"API_TOKEN_ASSIGNMENT":2}}',
            findings_json='[{"evidence":"apiKey=****"}]',
            duration_ms=3,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add_all(
        [
            ReviewQualityAcceptanceGate(
                id=9701,
                project_id=9101,
                title="缓存 Retriever 验收",
                change_type="RETRIEVER",
                status="PASSED",
                provider="DEEPSEEK",
                profile="backend-default-ai-review",
                risk_type="SECURITY",
                evaluation_case_ids_json="[9111]",
                evaluation_run_ids_json="[9401]",
                rule_gap_summary_json="[]",
                admission_json='{"problemStatement":"security false positive"}',
                exit_json='{"resultStatus":"IMPROVED","falsePositiveDelta":-1}',
                created_at=now,
                updated_at=now,
            ),
            ReviewQualityAcceptanceGate(
                id=9702,
                project_id=9102,
                title="其它项目验收",
                change_type="PROMPT",
                status="FAILED",
                provider="OPENAI",
                profile="backend-default-ai-review",
                risk_type="SECURITY",
                evaluation_case_ids_json="[9117]",
                evaluation_run_ids_json="[]",
                rule_gap_summary_json="[]",
                admission_json="{}",
                exit_json='{"resultStatus":"REGRESSED"}',
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()


def _case(
    case_id: int,
    project_id: int,
    task_id: int | None,
    risk_type: str,
    verdict: str,
    *,
    provider: str = "DEEPSEEK",
    source: str = "AI_FINDING",
) -> EvaluationCase:
    now = datetime.now()
    return EvaluationCase(
        id=case_id,
        task_id=task_id,
        review_key="deepseek-main",
        finding_id=f"finding-{case_id}",
        fingerprint=f"fp-{case_id}",
        project_id=project_id,
        provider=provider,
        profile="backend-default-ai-review",
        risk_type=risk_type,
        severity="MAJOR",
        context_status="PARTIAL",
        verdict=verdict,
        human_comment="quality dashboard sample",
        source=source,
        item_snapshot_json='{"title":"sample"}',
        created_at=now,
        updated_at=now,
    )
