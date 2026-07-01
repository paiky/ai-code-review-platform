from __future__ import annotations

from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewResult
from app.project_integration.models import Project
from app.review_feedback.service import ai_finding_fingerprint
from app.review_record.models import ReviewTask


def seed_evaluation_task(db_session: Session) -> str:
    db_session.add(
        Project(
            id=7101,
            name="evaluation-demo-service",
            git_provider="GITLAB",
            git_project_id="evaluation-7101",
            repository_url="https://gitlab.example.com/demo/evaluation",
            default_template_code="backend-default",
            default_code_quality_profile_code="backend-default-ai-review",
            default_code_quality_provider_code="DEEPSEEK",
            status="ENABLED",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    )
    db_session.add(
        ReviewTask(
            id=7201,
            project_id=7101,
            trigger_type="GITLAB_MR_WEBHOOK",
            external_source_id="88",
            external_url="https://gitlab.example.com/demo/evaluation/-/merge_requests/88",
            source_branch="feature/evaluation",
            target_branch="main",
            template_code="backend-default",
            code_quality_profile_code="backend-default-ai-review",
            status="SUCCESS",
            review_status="MAJOR",
            risk_level="HIGH",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    )
    findings = [
        {
            "findingId": "finding-transaction-1",
            "severity": "MAJOR",
            "category": "TRANSACTION",
            "filePath": "src/main/java/demo/OrderService.java",
            "startLine": 42,
            "endLine": 48,
            "title": "订单创建缺少事务边界",
            "body": "该方法同时写订单和流水，部分失败会造成数据不一致。",
            "suggestion": "为入口方法增加事务。",
            "confidence": "HIGH",
            "contextStatus": "PARTIAL",
            "source": "DEEPSEEK",
        }
    ]
    result = CodeQualityReviewResult(
        id=7301,
        task_id=7201,
        review_key="deepseek-main",
        project_id=7101,
        profile_code="backend-default-ai-review",
        provider="DEEPSEEK",
        model="deepseek-v4-pro",
        display_name="DeepSeek 主审",
        sort_order=10,
        status="SUCCESS",
        overall_level="MAJOR",
        summary="发现 1 个事务问题。",
        finding_count=1,
        findings_json=json.dumps(findings, ensure_ascii=False),
        raw_output=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db_session.add(result)
    db_session.commit()
    return ai_finding_fingerprint(result, findings[0], 0)


def test_create_evaluation_case_from_ai_finding_enriches_source_fields(
    client: TestClient,
    db_session: Session,
) -> None:
    fingerprint = seed_evaluation_task(db_session)

    response = client.post(
        "/api/evaluation-cases",
        json={
            "source": "AI_FINDING",
            "taskId": 7201,
            "reviewKey": "deepseek-main",
            "fingerprint": fingerprint,
            "verdict": "TRUE_POSITIVE",
            "humanComment": "确认是真问题。",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["taskId"] == 7201
    assert data["projectId"] == 7101
    assert data["reviewKey"] == "deepseek-main"
    assert data["findingId"] == "finding-transaction-1"
    assert data["fingerprint"] == fingerprint
    assert data["provider"] == "DEEPSEEK"
    assert data["profile"] == "backend-default-ai-review"
    assert data["riskType"] == "TRANSACTION"
    assert data["severity"] == "MAJOR"
    assert data["contextStatus"] == "PARTIAL"
    assert data["verdict"] == "TRUE_POSITIVE"
    assert data["humanComment"] == "确认是真问题。"
    assert data["itemSnapshot"]["title"] == "订单创建缺少事务边界"


def test_manual_evaluation_case_create_query_and_update(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_evaluation_task(db_session)

    created = client.post(
        "/api/evaluation-cases",
        json={
            "source": "MANUAL",
            "projectId": 7101,
            "provider": "OPENAI",
            "profile": "backend-default-ai-review",
            "riskType": "SECURITY",
            "severity": "CRITICAL",
            "contextStatus": "INSUFFICIENT",
            "verdict": "MISSING_FINDING",
            "humanComment": "人工发现鉴权漏报。",
            "itemSnapshot": {"title": "缺少鉴权"},
        },
    )

    assert created.status_code == 200
    case_id = created.json()["data"]["id"]

    listed = client.get(
        "/api/evaluation-cases",
        params={
            "projectId": 7101,
            "provider": "OPENAI",
            "profile": "backend-default-ai-review",
            "riskType": "SECURITY",
            "verdict": "MISSING_FINDING",
        },
    )
    assert listed.status_code == 200
    page = listed.json()["data"]
    assert page["total"] == 1
    assert page["items"][0]["id"] == case_id
    assert page["items"][0]["itemSnapshot"]["title"] == "缺少鉴权"

    updated = client.put(
        f"/api/evaluation-cases/{case_id}",
        json={"verdict": "CONTEXT_MISSING", "humanComment": "需要调用方上下文。"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["verdict"] == "CONTEXT_MISSING"
    assert updated.json()["data"]["humanComment"] == "需要调用方上下文。"

    fetched = client.get(f"/api/evaluation-cases/{case_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["verdict"] == "CONTEXT_MISSING"


def test_evaluation_case_rejects_invalid_verdict(client: TestClient, db_session: Session) -> None:
    seed_evaluation_task(db_session)

    response = client.post(
        "/api/evaluation-cases",
        json={"source": "MANUAL", "projectId": 7101, "verdict": "NOT_A_VERDICT"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_ai_finding_evaluation_case_requires_existing_source(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_evaluation_task(db_session)

    missing_task = client.post(
        "/api/evaluation-cases",
        json={
            "source": "AI_FINDING",
            "taskId": 999999,
            "fingerprint": "missing",
            "verdict": "UNKNOWN",
        },
    )
    assert missing_task.status_code == 404
    assert missing_task.json()["code"] == "RESOURCE_NOT_FOUND"

    missing_finding = client.post(
        "/api/evaluation-cases",
        json={
            "source": "AI_FINDING",
            "taskId": 7201,
            "reviewKey": "deepseek-main",
            "fingerprint": "missing",
            "verdict": "UNKNOWN",
        },
    )
    assert missing_finding.status_code == 404
    assert missing_finding.json()["code"] == "RESOURCE_NOT_FOUND"
