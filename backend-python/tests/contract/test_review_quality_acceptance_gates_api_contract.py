from __future__ import annotations

from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.evaluation.models import EvaluationCase, EvaluationRun
from app.project_integration.models import Project


def test_acceptance_gate_empty_list_is_explainable(client: TestClient) -> None:
    response = client.get("/api/review-quality/acceptance-gates")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0
    assert "No review quality acceptance gate record" in data["explanation"]


def test_create_acceptance_gate_saves_admission_links_and_safe_rule_gap_summary(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_acceptance_project_case_and_run(db_session)

    response = client.post(
        "/api/review-quality/acceptance-gates",
        json={
            "projectId": 9201,
            "title": "补缓存 Retriever 准入",
            "changeType": "RETRIEVER",
            "status": "ADMITTED",
            "provider": "DEEPSEEK",
            "profile": "backend-default-ai-review",
            "riskType": "CACHE_CONSISTENCY",
            "evaluationCaseIds": [9211],
            "evaluationRunIds": [9221],
            "ruleGapSummary": [
                {
                    "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
                    "signal": "CACHE_WRITE_DELETE_CHANGED",
                    "requestedContext": "CACHE_USAGE_CONTEXT",
                    "suggestedCapability": r"Add cache retriever D:\projects\private\repo; token: super-secret-token",
                    "summaryKey": "cache-gap",
                    "sourceSnippet": "line with source code",
                    "providerRawOutput": "provider raw output",
                    "diffText": "diff --git a/secret b/secret",
                }
            ],
            "admission": {
                "problemStatement": "缓存误判集中；Authorization: Bearer super-secret-token",
                "expectedBenefit": "降低缓存误判",
                "riskAssessment": r"检索耗时增加 D:\projects\private\repo",
                "costEstimate": "低成本",
                "decisionBy": "admin",
                "decisionAt": "2026-07-02T10:00:00+08:00",
            },
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["projectId"] == 9201
    assert data["projectName"] == "acceptance-gate-service"
    assert data["title"] == "补缓存 Retriever 准入"
    assert data["changeType"] == "RETRIEVER"
    assert data["status"] == "ADMITTED"
    assert data["evaluationCaseIds"] == [9211]
    assert data["evaluationRunIds"] == [9221]
    assert data["evaluationCaseCount"] == 1
    assert data["evaluationRunCount"] == 1
    assert data["ruleGapSummary"][0]["summaryKey"] == "cache-gap"
    assert data["admission"]["decisionBy"] == "admin"
    payload = json.dumps(data, ensure_ascii=False)
    assert "super-secret-token" not in payload
    assert r"D:\projects" not in payload
    assert "line with source code" not in payload
    assert "provider raw output" not in payload
    assert "diff --git" not in payload
    assert "Authorization: ****" in payload


def test_update_acceptance_gate_exit_result_saves_delta_and_result_status(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_acceptance_project_case_and_run(db_session)
    gate = client.post(
        "/api/review-quality/acceptance-gates",
        json={
            "projectId": 9201,
            "title": "Prompt 调整准入",
            "changeType": "PROMPT",
            "evaluationCaseIds": [9211],
            "evaluationRunIds": [9221],
        },
    ).json()["data"]

    response = client.put(
        f"/api/review-quality/acceptance-gates/{gate['id']}",
        json={
            "status": "PASSED",
            "exit": {
                "resultStatus": "IMPROVED",
                "falsePositiveDelta": -2,
                "contextMissingDelta": -1,
                "missingFindingDelta": 0,
                "findingCountDelta": -3,
                "durationDeltaMs": 120,
                "tokenCostDelta": 12.5,
                "notes": "candidate improved target samples; apiKey: secret-key",
                "decidedBy": "review-admin",
                "decidedAt": "2026-07-02T11:00:00+08:00",
            },
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "PASSED"
    assert data["exit"]["resultStatus"] == "IMPROVED"
    assert data["exit"]["falsePositiveDelta"] == -2
    assert data["exit"]["tokenCostDelta"] == 12.5
    assert data["coreDelta"]["resultStatus"] == "IMPROVED"
    assert "secret-key" not in json.dumps(data, ensure_ascii=False)


def test_acceptance_gate_filters_project_change_type_status_provider_profile_and_risk_type(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_acceptance_project_case_and_run(db_session)
    _seed_project(db_session, 9202, "other-acceptance-service")
    db_session.commit()

    first = client.post(
        "/api/review-quality/acceptance-gates",
        json={
            "projectId": 9201,
            "title": "目标记录",
            "changeType": "RULE",
            "status": "RUNNING_VALIDATION",
            "provider": "DEEPSEEK",
            "profile": "backend-default-ai-review",
            "riskType": "SECURITY",
        },
    ).json()["data"]
    client.post(
        "/api/review-quality/acceptance-gates",
        json={
            "projectId": 9202,
            "title": "非目标记录",
            "changeType": "PROVIDER",
            "status": "FAILED",
            "provider": "GLM",
            "profile": "frontend-default-ai-review",
            "riskType": "TRANSACTION",
        },
    )

    response = client.get(
        "/api/review-quality/acceptance-gates",
        params={
            "projectId": 9201,
            "changeType": "RULE",
            "status": "RUNNING_VALIDATION",
            "provider": "DEEPSEEK",
            "profile": "backend-default-ai-review",
            "riskType": "SECURITY",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["id"] == first["id"]
    assert data["items"][0]["evaluationCaseCount"] == 0
    assert "ruleGapSummary" not in data["items"][0]


def test_acceptance_gate_rejects_invalid_enum_missing_project_and_missing_links(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_acceptance_project_case_and_run(db_session)

    invalid = client.post(
        "/api/review-quality/acceptance-gates",
        json={"projectId": 9201, "title": "bad", "changeType": "NOT_A_CHANGE"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "VALIDATION_ERROR"

    missing_project = client.post(
        "/api/review-quality/acceptance-gates",
        json={"projectId": 999999, "title": "bad", "changeType": "RULE"},
    )
    assert missing_project.status_code == 404
    assert missing_project.json()["code"] == "RESOURCE_NOT_FOUND"

    missing_case = client.post(
        "/api/review-quality/acceptance-gates",
        json={"projectId": 9201, "title": "bad", "evaluationCaseIds": [999999]},
    )
    assert missing_case.status_code == 404
    assert missing_case.json()["code"] == "RESOURCE_NOT_FOUND"

    missing_run = client.post(
        "/api/review-quality/acceptance-gates",
        json={"projectId": 9201, "title": "bad", "evaluationRunIds": [999999]},
    )
    assert missing_run.status_code == 404
    assert missing_run.json()["code"] == "RESOURCE_NOT_FOUND"


def _seed_acceptance_project_case_and_run(db_session: Session) -> None:
    now = datetime.now()
    _seed_project(db_session, 9201, "acceptance-gate-service")
    db_session.add(
        EvaluationCase(
            id=9211,
            task_id=9301,
            review_key="deepseek-main",
            finding_id="finding-cache-1",
            fingerprint="fp-cache-1",
            project_id=9201,
            provider="DEEPSEEK",
            profile="backend-default-ai-review",
            risk_type="CACHE_CONSISTENCY",
            severity="MAJOR",
            context_status="PARTIAL",
            verdict="FALSE_POSITIVE",
            human_comment="cache sample",
            source="AI_FINDING",
            item_snapshot_json='{"title":"cache finding"}',
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        EvaluationRun(
            id=9221,
            name="cache retriever replay",
            run_type="REVIEW_REPLAY",
            sample_set_name="cache-regression",
            sample_set_json='{"caseIds":[9211],"count":1}',
            project_id=9201,
            provider="DEEPSEEK",
            profile="backend-default-ai-review",
            model="deepseek-v4-pro",
            prompt_hash="sha256-demo",
            context_pack_version="context-pack-v0",
            retriever_version="local-retriever-v0",
            rule_gap_version="rule-gap-v0",
            status="COMPLETED",
            total_count=1,
            completed_count=1,
            failed_count=0,
            result_summary_json='{"totalCount":1}',
            duration_ms=1000,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def _seed_project(db_session: Session, project_id: int, name: str) -> None:
    now = datetime.now()
    db_session.add(
        Project(
            id=project_id,
            name=name,
            git_provider="GITLAB",
            git_project_id=f"acceptance-{project_id}",
            repository_url=f"https://gitlab.example.com/demo/{name}",
            default_template_code="backend-default",
            default_code_quality_profile_code="backend-default-ai-review",
            default_code_quality_provider_code="DEEPSEEK",
            status="ENABLED",
            created_at=now,
            updated_at=now,
        )
    )
