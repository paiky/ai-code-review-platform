from __future__ import annotations

from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewProgressEvent, CodeQualityReviewResult
from app.evaluation.models import EvaluationCase
from app.project_integration.models import Project
from app.review_feedback.service import ai_finding_fingerprint
from app.review_record.models import ReviewTask


def test_rule_gap_attribution_empty_state_is_explainable(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_project_task_and_result(db_session)
    case = _manual_case(88101)
    db_session.add(case)
    db_session.commit()

    response = client.get("/api/evaluation-cases/88101/rule-gap-attribution")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["attributionType"] is None
    assert data["ruleGapSummary"] == []
    assert "has not been recorded" in data["explanation"]


def test_rule_gap_attribution_update_and_case_response_are_safe(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_project_task_and_result(db_session)
    db_session.add(_manual_case(88102))
    db_session.commit()

    response = client.put(
        "/api/evaluation-cases/88102/rule-gap-attribution",
        json={
            "attributionType": "RULE_GAP_CAUSED",
            "attributedBy": "admin",
            "comment": "需要补缓存检索；token: super-secret-token",
            "ruleGapSummary": [
                {
                    "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
                    "signal": "CACHE_WRITE_DELETE_CHANGED",
                    "requestedContext": "CACHE_USAGE_CONTEXT",
                    "suggestedCapability": r"Add cache retriever D:\projects\private\repo; token: super-secret-token",
                    "taskId": 88201,
                    "reviewKey": "deepseek-main",
                    "progressEventId": 88301,
                    "sourceSnippet": "line with source code",
                    "providerRawOutput": "provider raw output",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["attributionType"] == "RULE_GAP_CAUSED"
    assert data["ruleGapSummary"][0]["gapType"] == "UNSUPPORTED_PLANNER_SIGNAL"
    payload = json.dumps(data, ensure_ascii=False)
    assert "super-secret-token" not in payload
    assert r"D:\projects" not in payload
    assert "line with source code" not in payload
    assert "provider raw output" not in payload
    assert "token: ****" in payload

    fetched = client.get("/api/evaluation-cases/88102")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["ruleGapAttribution"]["attributionType"] == "RULE_GAP_CAUSED"


def test_rule_gap_attribution_rejects_invalid_enum(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_project_task_and_result(db_session)
    db_session.add(_manual_case(88103))
    db_session.commit()

    response = client.put(
        "/api/evaluation-cases/88103/rule-gap-attribution",
        json={"attributionType": "NOT_A_REAL_ATTRIBUTION"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_ai_finding_case_auto_captures_latest_context_pack_rule_gap_summary_safely(
    client: TestClient,
    db_session: Session,
) -> None:
    fingerprint = _seed_project_task_and_result(db_session)
    db_session.add(
        CodeQualityReviewProgressEvent(
            id=88301,
            task_id=88201,
            review_key="deepseek-main",
            phase="CONTEXT_PACK_BUILT",
            level="INFO",
            message="Context Pack 已构建",
            detail=json.dumps(
                {
                    "summary": {
                        "ruleGapItems": [
                            {
                                "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
                                "signal": "CACHE_WRITE_DELETE_CHANGED",
                                "requestedContext": "CACHE_USAGE_CONTEXT",
                                "suggestedCapability": (
                                    r"Add cache retriever D:\projects\private\repo; "
                                    "Authorization: Bearer super-secret-token"
                                ),
                                "sourceSnippet": "line with source code",
                                "providerRawOutput": "provider raw output",
                            }
                        ]
                    }
                },
                ensure_ascii=False,
            ),
            created_at=datetime.now(),
        )
    )
    db_session.commit()

    response = client.post(
        "/api/evaluation-cases",
        json={
            "source": "AI_FINDING",
            "taskId": 88201,
            "reviewKey": "deepseek-main",
            "fingerprint": fingerprint,
            "verdict": "CONTEXT_MISSING",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    summary = data["ruleGapAttribution"]["ruleGapSummary"]
    assert summary[0]["gapType"] == "UNSUPPORTED_PLANNER_SIGNAL"
    assert summary[0]["signal"] == "CACHE_WRITE_DELETE_CHANGED"
    assert summary[0]["progressEventId"] == 88301
    payload = json.dumps(data, ensure_ascii=False)
    assert "super-secret-token" not in payload
    assert r"D:\projects" not in payload
    assert "line with source code" not in payload
    assert "provider raw output" not in payload


def test_quality_and_rule_gap_dashboards_include_attribution_summary(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_project_task_and_result(db_session)
    now = datetime.now()
    db_session.add_all(
        [
            CodeQualityReviewProgressEvent(
                id=88311,
                task_id=88201,
                review_key="deepseek-main",
                phase="CONTEXT_PACK_BUILT",
                level="INFO",
                message="Context Pack 已构建",
                detail=_context_pack_detail("CACHE_WRITE_DELETE_CHANGED"),
                created_at=now,
            ),
            CodeQualityReviewProgressEvent(
                id=88312,
                task_id=88202,
                review_key="deepseek-main",
                phase="CONTEXT_PACK_BUILT",
                level="INFO",
                message="Context Pack 已构建",
                detail=_context_pack_detail("MQ_CONFIG_CHANGED"),
                created_at=now,
            ),
            _manual_case(
                88111,
                task_id=88201,
                verdict="FALSE_POSITIVE",
                attribution_type="RULE_GAP_CAUSED",
                signal="CACHE_WRITE_DELETE_CHANGED",
            ),
            _manual_case(
                88112,
                task_id=88202,
                verdict="FALSE_POSITIVE",
                attribution_type=None,
                signal="MQ_CONFIG_CHANGED",
            ),
        ]
    )
    db_session.commit()

    quality = client.get("/api/review-quality/dashboard?projectId=88101")
    assert quality.status_code == 200
    attribution = quality.json()["data"]["ruleGapAttributionSummary"]
    assert attribution["attributedCaseCount"] == 1
    assert attribution["unattributedCaseCount"] == 1
    assert attribution["causedOrRelatedCount"] == 1
    assert attribution["attributionTypeCounts"]["RULE_GAP_CAUSED"] == 1
    assert attribution["verdictCounts"]["FALSE_POSITIVE"] == 1

    rule_gaps = client.get("/api/code-quality-reviews/rule-gaps?projectId=88101&recentDays=30&limit=10")
    assert rule_gaps.status_code == 200
    recommendations = rule_gaps.json()["data"]["recommendations"]["items"]
    proven = next(item for item in recommendations if item["signal"] == "CACHE_WRITE_DELETE_CHANGED")
    frequency_only = next(item for item in recommendations if item["signal"] == "MQ_CONFIG_CHANGED")
    assert proven["recommendationBasis"] == "PROVEN_BY_EVALUATION_CASES"
    assert proven["attributionSignals"]["causedOrRelatedCount"] == 1
    assert any("评估样本证明" in reason for reason in proven["reasons"])
    assert frequency_only["recommendationBasis"] == "FREQUENCY_ONLY"
    assert frequency_only["attributionSignals"]["causedOrRelatedCount"] == 0


def _seed_project_task_and_result(db_session: Session) -> str:
    now = datetime.now()
    db_session.add(
        Project(
            id=88101,
            name="rule-gap-attribution-service",
            git_provider="GITLAB",
            git_project_id="rule-gap-88101",
            repository_url="https://gitlab.example.com/demo/rule-gap-attribution",
            default_template_code="backend-default",
            default_code_quality_profile_code="backend-default-ai-review",
            default_code_quality_provider_code="DEEPSEEK",
            status="ENABLED",
            created_at=now,
            updated_at=now,
        )
    )
    for task_id in (88201, 88202):
        db_session.add(
            ReviewTask(
                id=task_id,
                project_id=88101,
                trigger_type="GITLAB_MR_WEBHOOK",
                external_source_id=str(task_id),
                external_url=f"https://gitlab.example.com/demo/rule-gap-attribution/-/merge_requests/{task_id}",
                source_branch="feature/rule-gap-attribution",
                target_branch="main",
                template_code="backend-default",
                code_quality_profile_code="backend-default-ai-review",
                status="SUCCESS",
                review_status="MAJOR",
                risk_level="HIGH",
                created_at=now,
                updated_at=now,
            )
        )
    findings = [
        {
            "findingId": "finding-rule-gap-1",
            "severity": "MAJOR",
            "category": "CACHE_CONSISTENCY",
            "filePath": "src/main/java/demo/OrderService.java",
            "title": "缓存删除缺少调用方上下文",
            "contextStatus": "PARTIAL",
        }
    ]
    result = CodeQualityReviewResult(
        id=88401,
        task_id=88201,
        review_key="deepseek-main",
        project_id=88101,
        profile_code="backend-default-ai-review",
        provider="DEEPSEEK",
        model="deepseek-v4-pro",
        display_name="DeepSeek 主审",
        sort_order=10,
        status="SUCCESS",
        overall_level="MAJOR",
        summary="发现 1 个缓存问题。",
        finding_count=1,
        findings_json=json.dumps(findings, ensure_ascii=False),
        raw_output=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add(result)
    db_session.commit()
    return ai_finding_fingerprint(result, findings[0], 0)


def _manual_case(
    case_id: int,
    *,
    task_id: int | None = None,
    verdict: str = "FALSE_POSITIVE",
    attribution_type: str | None = None,
    signal: str | None = None,
) -> EvaluationCase:
    now = datetime.now()
    rule_gap_summary = []
    if signal:
        rule_gap_summary = [
            {
                "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
                "signal": signal,
                "requestedContext": "CACHE_USAGE_CONTEXT"
                if signal == "CACHE_WRITE_DELETE_CHANGED"
                else "MQ_CONFIG_CONTEXT",
                "suggestedCapability": "Add cache retriever."
                if signal == "CACHE_WRITE_DELETE_CHANGED"
                else "Add MQ retriever.",
                "taskId": task_id,
                "reviewKey": "deepseek-main",
                "summaryKey": signal,
            }
        ]
    return EvaluationCase(
        id=case_id,
        task_id=task_id,
        review_key="deepseek-main",
        finding_id=f"finding-{case_id}",
        fingerprint=f"fp-{case_id}",
        project_id=88101,
        provider="DEEPSEEK",
        profile="backend-default-ai-review",
        risk_type="CACHE_CONSISTENCY",
        severity="MAJOR",
        context_status="PARTIAL",
        verdict=verdict,
        human_comment="rule gap attribution sample",
        source="AI_FINDING",
        item_snapshot_json='{"title":"sample"}',
        rule_gap_attribution_type=attribution_type,
        rule_gap_summary_json=json.dumps(rule_gap_summary, ensure_ascii=False),
        rule_gap_attribution_comment="manual attribution" if attribution_type else None,
        rule_gap_attributed_by="admin" if attribution_type else None,
        rule_gap_attributed_at=now if attribution_type else None,
        created_at=now,
        updated_at=now,
    )


def _context_pack_detail(signal: str) -> str:
    return json.dumps(
        {
            "summary": {
                "ruleGapItems": [
                    {
                        "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
                        "signal": signal,
                        "requestedContext": "CACHE_USAGE_CONTEXT"
                        if signal == "CACHE_WRITE_DELETE_CHANGED"
                        else "MQ_CONFIG_CONTEXT",
                        "suggestedCapability": "Add cache retriever."
                        if signal == "CACHE_WRITE_DELETE_CHANGED"
                        else "Add MQ retriever.",
                    }
                ]
            }
        },
        ensure_ascii=False,
    )
