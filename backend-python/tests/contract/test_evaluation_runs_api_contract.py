from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.evaluation.models import EvaluationCase
from app.project_integration.models import Project


def seed_evaluation_run_cases(db_session: Session) -> list[int]:
    db_session.add(
        Project(
            id=8101,
            name="evaluation-run-demo-service",
            git_provider="GITLAB",
            git_project_id="evaluation-run-8101",
            repository_url="https://gitlab.example.com/demo/evaluation-run",
            default_template_code="backend-default",
            default_code_quality_profile_code="backend-default-ai-review",
            default_code_quality_provider_code="DEEPSEEK",
            status="ENABLED",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    )
    cases = [
        EvaluationCase(
            id=8111,
            task_id=8201,
            review_key="deepseek-main",
            finding_id="finding-auth-1",
            fingerprint="fingerprint-auth-1",
            project_id=8101,
            provider="DEEPSEEK",
            profile="backend-default-ai-review",
            risk_type="SECURITY",
            severity="MAJOR",
            context_status="PARTIAL",
            verdict="FALSE_POSITIVE",
            human_comment="鉴权由网关注入。",
            source="AI_FINDING",
            item_snapshot_json='{"title":"接口缺少鉴权"}',
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ),
        EvaluationCase(
            id=8112,
            task_id=8202,
            review_key="deepseek-main",
            finding_id="finding-tx-1",
            fingerprint="fingerprint-tx-1",
            project_id=8101,
            provider="DEEPSEEK",
            profile="backend-default-ai-review",
            risk_type="TRANSACTION",
            severity="MAJOR",
            context_status="INSUFFICIENT",
            verdict="CONTEXT_MISSING",
            human_comment="需要调用方上下文。",
            source="AI_FINDING",
            item_snapshot_json='{"title":"事务上下文不足"}',
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ),
    ]
    db_session.add_all(cases)
    db_session.commit()
    return [case.id for case in cases]


def test_create_evaluation_run_initializes_items_and_lists_filters(
    client: TestClient,
    db_session: Session,
) -> None:
    case_ids = seed_evaluation_run_cases(db_session)

    created = client.post(
        "/api/evaluation-runs",
        json={
            "name": "backend prompt candidate replay",
            "runType": "REVIEW_REPLAY",
            "sampleSetName": "backend-security-regression",
            "caseIds": case_ids,
            "projectId": 8101,
            "provider": "DEEPSEEK",
            "profile": "backend-default-ai-review",
            "model": "deepseek-v4-pro",
            "promptHash": "sha256-new",
            "contextPackVersion": "context-pack-v0",
            "retrieverVersion": "local-retriever-v0",
            "ruleGapVersion": "rule-gap-v0",
            "baseline": {"label": "current-prod", "promptHash": "sha256-old"},
            "candidate": {"label": "m5-candidate", "promptHash": "sha256-new"},
            "notes": "M5 manual replay placeholder",
        },
    )

    assert created.status_code == 200
    data = created.json()["data"]
    assert data["name"] == "backend prompt candidate replay"
    assert data["runType"] == "REVIEW_REPLAY"
    assert data["sampleSetName"] == "backend-security-regression"
    assert data["sampleSet"]["caseIds"] == case_ids
    assert data["sampleSet"]["count"] == 2
    assert data["projectId"] == 8101
    assert data["projectName"] == "evaluation-run-demo-service"
    assert data["provider"] == "DEEPSEEK"
    assert data["profile"] == "backend-default-ai-review"
    assert data["model"] == "deepseek-v4-pro"
    assert data["promptHash"] == "sha256-new"
    assert data["contextPackVersion"] == "context-pack-v0"
    assert data["retrieverVersion"] == "local-retriever-v0"
    assert data["ruleGapVersion"] == "rule-gap-v0"
    assert data["baseline"]["label"] == "current-prod"
    assert data["candidate"]["label"] == "m5-candidate"
    assert data["status"] == "PENDING"
    assert data["totalCount"] == 2
    assert data["completedCount"] == 0
    assert data["failedCount"] == 0
    assert len(data["items"]) == 2
    assert data["items"][0]["caseId"] == case_ids[0]
    assert data["items"][0]["status"] == "PENDING"
    assert data["items"][0]["riskType"] == "SECURITY"
    assert data["items"][1]["caseId"] == case_ids[1]
    run_id = data["id"]

    listed = client.get(
        "/api/evaluation-runs",
        params={
            "projectId": 8101,
            "provider": "DEEPSEEK",
            "profile": "backend-default-ai-review",
            "runType": "REVIEW_REPLAY",
            "status": "PENDING",
        },
    )
    assert listed.status_code == 200
    page = listed.json()["data"]
    assert page["total"] == 1
    assert page["items"][0]["id"] == run_id
    assert "items" not in page["items"][0]

    fetched = client.get(f"/api/evaluation-runs/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["items"][0]["fingerprint"] == "fingerprint-auth-1"


def test_update_evaluation_run_item_refreshes_run_aggregate(
    client: TestClient,
    db_session: Session,
) -> None:
    case_ids = seed_evaluation_run_cases(db_session)
    created = client.post(
        "/api/evaluation-runs",
        json={
            "name": "candidate replay",
            "runType": "EVALUATION",
            "caseIds": case_ids,
            "provider": "DEEPSEEK",
            "profile": "backend-default-ai-review",
        },
    )
    run = created.json()["data"]
    first_item_id = run["items"][0]["id"]
    second_item_id = run["items"][1]["id"]

    updated = client.put(
        f"/api/evaluation-runs/{run['id']}/items/{first_item_id}",
        json={
            "status": "COMPLETED",
            "durationMs": 1234,
            "baselineSummary": {"findingCount": 2, "falsePositiveCount": 1, "overallLevel": "MAJOR"},
            "candidateSummary": {"findingCount": 1, "falsePositiveCount": 0, "overallLevel": "MINOR"},
            "resultSummary": {"matchedVerdict": True, "notes": "candidate reduced false positive"},
        },
    )

    assert updated.status_code == 200
    data = updated.json()["data"]
    assert data["status"] == "RUNNING"
    assert data["totalCount"] == 2
    assert data["completedCount"] == 1
    assert data["failedCount"] == 0
    assert data["durationMs"] == 1234
    assert data["resultSummary"]["statusCounts"]["COMPLETED"] == 1
    item = next(item for item in data["items"] if item["id"] == first_item_id)
    assert item["status"] == "COMPLETED"
    assert item["durationMs"] == 1234
    assert item["baselineSummary"]["falsePositiveCount"] == 1
    assert item["candidateSummary"]["findingCount"] == 1
    assert item["resultSummary"]["matchedVerdict"] is True

    failed = client.put(
        f"/api/evaluation-runs/{run['id']}/items/{second_item_id}",
        json={"status": "FAILED", "durationMs": 2000, "errorMessage": "manual replay failed"},
    )
    assert failed.status_code == 200
    failed_data = failed.json()["data"]
    assert failed_data["status"] == "FAILED"
    assert failed_data["completedCount"] == 1
    assert failed_data["failedCount"] == 1
    assert failed_data["durationMs"] == 3234
    assert failed_data["resultSummary"]["statusCounts"]["FAILED"] == 1


def test_evaluation_run_rejects_missing_cases_and_invalid_status(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_evaluation_run_cases(db_session)

    empty_cases = client.post("/api/evaluation-runs", json={"name": "bad", "caseIds": []})
    assert empty_cases.status_code == 400
    assert empty_cases.json()["code"] == "VALIDATION_ERROR"

    missing_case = client.post("/api/evaluation-runs", json={"name": "bad", "caseIds": [999999]})
    assert missing_case.status_code == 404
    assert missing_case.json()["code"] == "RESOURCE_NOT_FOUND"

    run = client.post("/api/evaluation-runs", json={"name": "ok", "caseIds": [8111]}).json()["data"]
    invalid_status = client.put(
        f"/api/evaluation-runs/{run['id']}/items/{run['items'][0]['id']}",
        json={"status": "NOT_A_STATUS"},
    )
    assert invalid_status.status_code == 400
    assert invalid_status.json()["code"] == "VALIDATION_ERROR"


def test_evaluation_run_item_update_is_scoped_to_run(
    client: TestClient,
    db_session: Session,
) -> None:
    case_ids = seed_evaluation_run_cases(db_session)
    first = client.post("/api/evaluation-runs", json={"name": "first", "caseIds": [case_ids[0]]}).json()["data"]
    second = client.post("/api/evaluation-runs", json={"name": "second", "caseIds": [case_ids[1]]}).json()["data"]

    response = client.put(
        f"/api/evaluation-runs/{first['id']}/items/{second['items'][0]['id']}",
        json={"status": "COMPLETED"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
