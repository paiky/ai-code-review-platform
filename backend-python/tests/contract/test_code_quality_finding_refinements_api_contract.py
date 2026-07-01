from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewResult
from app.project_integration.models import GitLabMergeRequestEvent, Project
from app.review_feedback.service import ai_finding_fingerprint
from app.review_record.models import ReviewTask


def test_create_refinement_by_fingerprint_returns_completed_safe_overlay(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    fingerprints = _seed_refinement_task(db_session)
    monkeypatch.setattr(
        "app.code_quality.service.build_review_context_pack",
        lambda *args, **kwargs: _context_pack("PREPARED"),
    )

    response = client.post(
        "/api/review-tasks/8201/code-quality-refinements",
        json={"reviewKey": "deepseek-main", "fingerprint": fingerprints[0]},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "COMPLETED"
    assert data["taskId"] == 8201
    assert data["reviewKey"] == "deepseek-main"
    assert data["findingIndex"] == 0
    assert data["fingerprint"] == fingerprints[0]
    assert data["retrievalPlan"]["plannerSignalCount"] == 1
    assert data["evidenceSummary"]["localRepository"]["status"] == "PREPARED"
    assert data["evidenceSummary"]["searches"][0]["includedSnippetCount"] == 1

    listed = client.get("/api/review-tasks/8201/code-quality-refinements?reviewKey=deepseek-main")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["id"] == data["id"]

    results = client.get("/api/review-tasks/8201/code-quality-results")
    finding = results.json()["data"][0]["findings"][0]
    assert finding["severity"] == "MAJOR"
    assert finding["contextStatus"] == "PARTIAL"
    assert finding["refinementOverlay"]["status"] == "COMPLETED"

    text = json.dumps(data, ensure_ascii=False)
    assert "super-secret" not in text
    assert "Authorization: Bearer" not in text
    assert "D:\\projects" not in text
    assert "line with secret source" not in text
    assert "provider raw output" not in text
    assert "promptText" not in text


def test_create_refinement_by_finding_index_returns_existing_without_force(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _seed_refinement_task(db_session)
    calls = {"count": 0}

    def fake_context(*args, **kwargs):
        calls["count"] += 1
        return _context_pack("PREPARED")

    monkeypatch.setattr("app.code_quality.service.build_review_context_pack", fake_context)

    first = client.post(
        "/api/review-tasks/8201/code-quality-refinements",
        json={"reviewKey": "deepseek-main", "findingIndex": 0},
    )
    second = client.post(
        "/api/review-tasks/8201/code-quality-refinements",
        json={"reviewKey": "deepseek-main", "findingIndex": 0},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert calls["count"] == 1


def test_refinement_rejects_non_candidate_findings(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _seed_refinement_task(db_session)
    monkeypatch.setattr(
        "app.code_quality.service.build_review_context_pack",
        lambda *args, **kwargs: _context_pack("PREPARED"),
    )

    minor = client.post(
        "/api/review-tasks/8201/code-quality-refinements",
        json={"reviewKey": "deepseek-main", "findingIndex": 1},
    )
    full = client.post(
        "/api/review-tasks/8201/code-quality-refinements",
        json={"reviewKey": "deepseek-main", "findingIndex": 2},
    )

    assert minor.status_code == 400
    assert minor.json()["code"] == "VALIDATION_ERROR"
    assert full.status_code == 400
    assert full.json()["code"] == "VALIDATION_ERROR"
    assert client.get("/api/review-tasks/8201/code-quality-refinements").json()["data"] == []


def test_refinement_failure_is_recorded_without_changing_original_result(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _seed_refinement_task(db_session)
    monkeypatch.setattr(
        "app.code_quality.service.build_review_context_pack",
        lambda *args, **kwargs: _context_pack("DISABLED"),
    )

    response = client.post(
        "/api/review-tasks/8201/code-quality-refinements",
        json={"reviewKey": "deepseek-main", "findingIndex": 0},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "FAILED"
    assert "Local repository" in data["failureReason"]

    results = client.get("/api/review-tasks/8201/code-quality-results").json()["data"]
    finding = results[0]["findings"][0]
    assert finding["severity"] == "MAJOR"
    assert finding["contextStatus"] == "PARTIAL"
    assert finding["refinementOverlay"]["status"] == "FAILED"


def _seed_refinement_task(db_session: Session) -> list[str]:
    now = datetime.now()
    db_session.add(
        Project(
            id=8101,
            name="refinement-demo-service",
            git_provider="GITLAB",
            git_project_id="refinement-8101",
            repository_url="https://gitlab.example.com/demo/refinement",
            default_template_code="backend-default",
            default_code_quality_profile_code="backend-default-ai-review",
            default_code_quality_provider_code="DEEPSEEK",
            status="ENABLED",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        ReviewTask(
            id=8201,
            project_id=8101,
            trigger_type="GITLAB_MR_WEBHOOK",
            external_source_id="99",
            source_branch="feature/refinement",
            target_branch="main",
            commit_sha="abcdef1234567890",
            template_code="backend-default",
            code_quality_profile_code="backend-default-ai-review",
            status="SUCCESS",
            review_status="MAJOR",
            risk_level="HIGH",
            created_at=now,
            updated_at=now,
        )
    )
    files = [
        {
            "path": "src/main/java/demo/OrderService.java",
            "newPath": "src/main/java/demo/OrderService.java",
            "diffText": "@@ -1,3 +1,4 @@\n public class OrderService {\n+  public void createOrder() {}\n }\n",
        }
    ]
    db_session.add(
        GitLabMergeRequestEvent(
            id=8301,
            task_id=8201,
            git_project_id="refinement-8101",
            project_name="refinement-demo-service",
            mr_id="99",
            event_action="open",
            event_time=now,
            source_branch="feature/refinement",
            target_branch="main",
            changed_files_summary=json.dumps({"files": files}, ensure_ascii=False),
            raw_payload="{}",
            created_at=now,
            updated_at=now,
        )
    )
    findings: list[dict[str, Any]] = [
        {
            "findingId": "finding-transaction-1",
            "severity": "MAJOR",
            "category": "TRANSACTION",
            "filePath": "src/main/java/demo/OrderService.java",
            "startLine": 2,
            "endLine": 2,
            "title": "订单创建缺少事务边界",
            "body": "该方法同时写订单和流水，部分失败会造成数据不一致。",
            "suggestion": "为入口方法增加事务。",
            "confidence": "HIGH",
            "contextStatus": "PARTIAL",
            "source": "DEEPSEEK",
        },
        {
            "findingId": "finding-minor-1",
            "severity": "MINOR",
            "category": "TEST_GAP",
            "filePath": "src/main/java/demo/OrderService.java",
            "startLine": 2,
            "title": "缺少测试",
            "contextStatus": "PARTIAL",
        },
        {
            "findingId": "finding-full-1",
            "severity": "MAJOR",
            "category": "TRANSACTION",
            "filePath": "src/main/java/demo/OrderService.java",
            "startLine": 2,
            "title": "上下文充分问题",
            "contextStatus": "FULL",
        },
    ]
    result = CodeQualityReviewResult(
        id=8401,
        task_id=8201,
        review_key="deepseek-main",
        project_id=8101,
        profile_code="backend-default-ai-review",
        provider="DEEPSEEK",
        model="deepseek-v4-pro",
        display_name="DeepSeek 主审",
        sort_order=10,
        status="SUCCESS",
        overall_level="MAJOR",
        summary="发现问题。",
        finding_count=len(findings),
        findings_json=json.dumps(findings, ensure_ascii=False),
        raw_output="provider raw output with token: super-secret",
        created_at=now,
        updated_at=now,
    )
    db_session.add(result)
    db_session.commit()
    return [ai_finding_fingerprint(result, finding, index) for index, finding in enumerate(findings)]


def _context_pack(local_repo_status: str) -> dict[str, Any]:
    local_repository = {
        "enabled": local_repo_status != "DISABLED",
        "status": local_repo_status,
        "failurePhase": "VALIDATE" if local_repo_status != "PREPARED" else None,
        "durationMs": 1,
        "sourceIncluded": False,
        "debugPath": "D:\\projects\\secret\\repo",
    }
    unavailable = []
    if local_repo_status != "PREPARED":
        unavailable.append(
            {
                "type": "LOCAL_REPOSITORY",
                "reason": "Local repository disabled; token: super-secret; D:\\projects\\secret\\repo",
            }
        )
    context_pack = {
        "version": "context-pack-v0",
        "changedFilesSummary": {"total": 1, "included": 1, "diffBytes": 128},
        "localRepositoryContext": local_repository,
        "localReferenceSearch": {
            "status": "RETRIEVED" if local_repo_status == "PREPARED" else "SKIPPED",
            "queryCount": 1 if local_repo_status == "PREPARED" else 0,
            "matchedFileCount": 1 if local_repo_status == "PREPARED" else 0,
            "includedSnippetCount": 1 if local_repo_status == "PREPARED" else 0,
            "truncated": False,
            "supportedSignalTypes": ["METHOD_SIGNATURE_CHANGED"],
            "skippedSignalTypes": [],
        },
        "localReferenceContext": {
            "status": "RETRIEVED" if local_repo_status == "PREPARED" else "SKIPPED",
            "summary": {
                "queryCount": 1 if local_repo_status == "PREPARED" else 0,
                "matchedFileCount": 1 if local_repo_status == "PREPARED" else 0,
                "includedSnippetCount": 1 if local_repo_status == "PREPARED" else 0,
                "truncated": False,
            },
            "searches": [
                {
                    "query": "createOrder",
                    "signalTypes": ["METHOD_SIGNATURE_CHANGED"],
                    "matchedFileCount": 1,
                    "candidateSnippetCount": 1,
                    "includedSnippetCount": 1,
                    "truncated": False,
                    "topMatchedPaths": ["src/main/java/demo/OrderFacade.java"],
                    "snippets": [{"lines": [{"text": "line with secret source"}]}],
                }
            ],
        },
        "contextPlan": {
            "plannerSignalCount": 1,
            "plannerSignalTotal": 1,
            "requestedContextCount": 1,
            "requestedContextTypeCounts": [{"type": "REFERENCE_SEARCH", "count": 1}],
        },
        "requestedContexts": [
            {"type": "REFERENCE_SEARCH", "available": local_repo_status == "PREPARED"},
        ],
        "unavailableContexts": unavailable,
        "plannerSignalTypeCounts": [{"type": "METHOD_SIGNATURE_CHANGED", "count": 1}],
        "retrieverSupportedSignalTypes": ["METHOD_SIGNATURE_CHANGED"],
        "retrieverUnsupportedSignalTypeCounts": [],
        "requestedContextAvailability": {"availableCount": 1 if local_repo_status == "PREPARED" else 0},
        "budgetCutSummary": {"maxTotalChars": 6000, "promptLength": 300},
        "notInjectedEvidence": {
            "items": [
                {
                    "type": "LOCAL_REFERENCE_SNIPPET",
                    "querySummary": "createOrder",
                    "topRelativePaths": ["src/main/java/demo/OrderFacade.java"],
                }
            ]
        },
        "ruleGapSummary": {"total": 0},
        "ruleGapItems": [],
        "providerRawOutput": "provider raw output",
        "promptText": "prompt should not be returned",
    }
    return {
        "reviewContext": {"mode": "FINDING_REFINEMENT"},
        "contextPack": context_pack,
        "localReferenceRetrieval": context_pack["localReferenceContext"],
        "promptText": "prompt should not be returned",
        "summary": {
            "localRepository": local_repository,
        },
        "meta": {"version": "context-pack-v0"},
    }
