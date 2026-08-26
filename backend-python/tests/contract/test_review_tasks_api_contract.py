from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.project_integration.models import GitLabMergeRequestEvent, Project
from app.code_quality.models import CodeQualityReviewResult
from app.review_record.models import NotificationRecord, ReviewResult, ReviewTask
from app.review_record.repository import refresh_review_status


def seed_review_task(db_session: Session) -> None:
    created_at = datetime(2026, 5, 18, 10, 0, 0)
    finished_at = datetime(2026, 5, 18, 10, 0, 8)
    db_session.add(
        Project(
            id=1,
            name="demo-service",
            git_provider="GITLAB",
            git_project_id="1001",
            repository_url="https://gitlab.example.com/demo/service",
            default_template_code="backend-default",
            default_code_quality_profile_code="backend-default-ai-review",
            default_code_quality_provider_code=None,
            dingtalk_webhook_id=None,
            status="ENABLED",
            description=None,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db_session.add(
        ReviewTask(
            id=10001,
            project_id=1,
            trigger_type="GITLAB_MR_WEBHOOK",
            external_source_id="12",
            external_url="https://gitlab.example.com/demo/service/-/merge_requests/12",
            source_branch="feature/risk-demo",
            target_branch="main",
            commit_sha="abcdef123456",
            before_sha=None,
            after_sha=None,
            author_name="Alice",
            author_username="alice",
            template_code="backend-default",
            status="SUCCESS",
            review_status="MAJOR",
            risk_level="HIGH",
            error_message=None,
            started_at=created_at,
            finished_at=finished_at,
            created_at=created_at,
            updated_at=finished_at,
        )
    )
    db_session.add(
        ReviewResult(
            id=20001,
            task_id=10001,
            project_id=1,
            template_code="backend-default",
            risk_level="HIGH",
            risk_item_count=2,
            change_analysis_json=json.dumps(
                {
                    "changeTypes": ["DB", "CACHE"],
                    "changedFileCount": 2,
                    "impactedResources": [],
                }
            ),
            risk_card_json=json.dumps(
                {
                    "riskLevel": "HIGH",
                    "riskItems": [
                        {"riskId": "risk-1", "riskLevel": "HIGH", "category": "DB", "ruleCode": "DB_SCHEMA_CHANGE"},
                        {"riskId": "risk-2", "riskLevel": "MEDIUM", "category": "CACHE", "ruleCode": "CACHE_CHANGE"},
                    ],
                    "focusIndicators": [{"category": "DB_SCHEMA", "riskLevel": "HIGH"}],
                }
            ),
            summary="涉及数据库和缓存变更",
            created_at=finished_at,
            updated_at=finished_at,
        )
    )
    db_session.add(
        CodeQualityReviewResult(
            id=50001,
            task_id=10001,
            project_id=1,
            profile_code="backend-default-ai-review",
            provider="DEEPSEEK",
            model="deepseek-chat",
            status="SUCCESS",
            overall_level="HIGH",
            summary="发现 2 个代码质量风险点",
            finding_count=2,
            findings_json="[]",
            raw_output=None,
            exit_code=None,
            error_message=None,
            started_at=created_at,
            finished_at=finished_at,
            created_at=finished_at,
            updated_at=finished_at,
        )
    )
    db_session.add(
        GitLabMergeRequestEvent(
            id=30001,
            task_id=10001,
            git_project_id="1001",
            project_name="demo-service",
            mr_id="12",
            event_action="open",
            event_time=created_at,
            source_branch="feature/risk-demo",
            target_branch="main",
            author_name="Alice",
            author_username="alice",
            changed_files_summary=json.dumps([{"path": "src/main/resources/db/V1.sql"}]),
            raw_payload=json.dumps({"object_kind": "merge_request"}),
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db_session.add(
        NotificationRecord(
            id=40001,
            task_id=10001,
            result_id=20001,
            channel="DINGTALK",
            target="研发质量群",
            status="SKIPPED",
            request_digest="DINGTALK_WEBHOOK_URL is empty",
            response_body=None,
            error_message=None,
            sent_at=None,
            created_at=finished_at,
            updated_at=finished_at,
        )
    )
    db_session.commit()


def test_review_tasks_read_api_contract(client: TestClient, db_session: Session) -> None:
    seed_review_task(db_session)

    list_response = client.get("/api/review-tasks", params={"keyword": "risk-demo"})
    assert list_response.status_code == 200
    list_data = list_response.json()["data"]
    assert list_data["total"] == 1
    item = list_data["items"][0]
    assert item["id"] == 10001
    assert item["projectName"] == "demo-service"
    assert item["reviewStatus"] == "MAJOR"
    assert item["riskLevel"] == "HIGH"
    assert item["riskItemCount"] == 2
    assert item["focusIndicators"] == [{"category": "DB_SCHEMA", "riskLevel": "HIGH"}]

    detail_response = client.get("/api/review-tasks/10001")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["gitProjectId"] == "1001"
    assert detail["mrId"] == "12"
    assert detail["eventAction"] == "open"
    assert detail["reviewStatus"] == "MAJOR"
    assert detail["changedFilesSummary"] == [{"path": "src/main/resources/db/V1.sql"}]
    assert detail["rawPayload"] == {"object_kind": "merge_request"}

    result_response = client.get("/api/review-tasks/10001/result")
    assert result_response.status_code == 200
    result = result_response.json()["data"]
    assert result["taskId"] == 10001
    assert result["changeAnalysis"]["changeTypes"] == ["DB", "CACHE"]
    assert result["riskCard"]["riskLevel"] == "HIGH"

    notification_response = client.get("/api/review-tasks/10001/notifications")
    assert notification_response.status_code == 200
    notifications = notification_response.json()["data"]
    assert notifications[0]["channel"] == "DINGTALK"
    assert notifications[0]["status"] == "SKIPPED"


def test_review_task_list_counts_ai_review_findings_instead_of_rule_reminders(
    client: TestClient, db_session: Session
) -> None:
    seed_review_task(db_session)
    result = db_session.get(ReviewResult, 20001)
    result.risk_item_count = 4
    risk_card = json.loads(result.risk_card_json)
    risk_card["riskItems"] = [
        {"riskId": f"risk-{index}", "riskLevel": "MEDIUM", "category": "DB", "ruleCode": "DB_SCHEMA_CHANGE"}
        for index in range(7)
    ]
    result.risk_card_json = json.dumps(risk_card)
    code_quality_result = db_session.get(CodeQualityReviewResult, 50001)
    code_quality_result.finding_count = 7
    db_session.commit()

    list_response = client.get("/api/review-tasks", params={"keyword": "risk-demo"})

    assert list_response.status_code == 200
    item = list_response.json()["data"]["items"][0]
    assert item["riskItemCount"] == 7


def test_review_task_list_review_status_aggregation_and_multi_select_filter(
    client: TestClient, db_session: Session
) -> None:
    seed_review_task(db_session)
    created_at = datetime(2026, 5, 18, 12, 0, 0)

    def add_task(task_id: int, status: str = "SUCCESS") -> None:
        db_session.add(
            ReviewTask(
                id=task_id,
                project_id=1,
                trigger_type="GITLAB_MR_WEBHOOK",
                external_source_id=str(task_id),
                template_code="backend-default",
                status=status,
                review_status="NOT_TRIGGERED",
                created_at=created_at,
                updated_at=created_at,
            )
        )

    def add_quality_result(
        task_id: int,
        review_key: str,
        status: str,
        findings: list[dict] | None = None,
        overall_level: str | None = None,
    ) -> None:
        findings = findings or []
        db_session.add(
            CodeQualityReviewResult(
                task_id=task_id,
                review_key=review_key,
                project_id=1,
                profile_code="backend-default-ai-review",
                provider="DEEPSEEK",
                status=status,
                overall_level=overall_level,
                finding_count=len(findings),
                findings_json=json.dumps(findings),
                created_at=created_at,
                updated_at=created_at,
            )
        )

    add_task(10002)
    add_task(10003)
    add_quality_result(10003, "running", "RUNNING")
    add_task(10004)
    add_quality_result(10004, "clean", "SUCCESS")
    add_task(10005)
    add_quality_result(10005, "minor", "SUCCESS", [{"severity": "MINOR"}])
    add_task(10006)
    add_quality_result(10006, "critical", "SUCCESS", [{"severity": "CRITICAL"}])
    add_task(10007)
    add_quality_result(10007, "failed", "FAILED")
    add_task(10008)
    add_quality_result(10008, "skipped", "SKIPPED")
    add_task(10009, "FAILED")
    add_task(10010)
    add_quality_result(10010, "success", "SUCCESS", [{"severity": "MAJOR"}])
    add_quality_result(10010, "failed", "FAILED")
    db_session.flush()

    for task_id in range(10002, 10011):
        refresh_review_status(db_session, task_id)
    db_session.commit()

    response = client.get("/api/review-tasks", params=[("reviewStatus", "CRITICAL"), ("reviewStatus", "TASK_FAILED")])

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["data"]["items"]} == {10006, 10009}
    assert db_session.get(ReviewTask, 10002).review_status == "NOT_TRIGGERED"
    assert db_session.get(ReviewTask, 10003).review_status == "REVIEWING"
    assert db_session.get(ReviewTask, 10004).review_status == "NO_RISK"
    assert db_session.get(ReviewTask, 10005).review_status == "MINOR"
    assert db_session.get(ReviewTask, 10006).review_status == "CRITICAL"
    assert db_session.get(ReviewTask, 10007).review_status == "REVIEW_FAILED"
    assert db_session.get(ReviewTask, 10008).review_status == "SKIPPED"
    assert db_session.get(ReviewTask, 10009).review_status == "TASK_FAILED"
    assert db_session.get(ReviewTask, 10010).review_status == "MAJOR"


def test_review_task_list_hides_focus_indicators_when_reminder_card_disabled(
    client: TestClient, db_session: Session
) -> None:
    seed_review_task(db_session)
    result = db_session.get(ReviewResult, 20001)
    result.reminder_card_enabled = False
    db_session.commit()

    list_response = client.get("/api/review-tasks", params={"keyword": "risk-demo"})

    assert list_response.status_code == 200
    item = list_response.json()["data"]["items"][0]
    assert item["focusIndicators"] == []


def test_review_tasks_trigger_type_filter(client: TestClient, db_session: Session) -> None:
    seed_review_task(db_session)
    created_at = datetime(2026, 5, 18, 11, 0, 0)
    db_session.add(
        ReviewTask(
            id=10002,
            project_id=1,
            trigger_type="GITLAB_PUSH_WEBHOOK",
            external_source_id="abc123",
            external_url="https://gitlab.example.com/demo/service/-/commit/abc123",
            source_branch="feature/push-demo",
            target_branch=None,
            commit_sha="abc123",
            before_sha="before123",
            after_sha="abc123",
            author_name="Bob",
            author_username="bob",
            template_code="backend-default",
            status="SUCCESS",
            risk_level="LOW",
            error_message=None,
            started_at=created_at,
            finished_at=created_at,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db_session.commit()

    mr_response = client.get("/api/review-tasks", params={"triggerType": "GITLAB_MR_WEBHOOK"})
    push_response = client.get("/api/review-tasks", params={"triggerType": "GITLAB_PUSH_WEBHOOK"})

    assert mr_response.status_code == 200
    assert push_response.status_code == 200
    assert mr_response.json()["data"]["total"] == 1
    assert mr_response.json()["data"]["items"][0]["triggerType"] == "GITLAB_MR_WEBHOOK"
    assert push_response.json()["data"]["total"] == 1
    assert push_response.json()["data"]["items"][0]["triggerType"] == "GITLAB_PUSH_WEBHOOK"


def test_review_tasks_target_type_filter_uses_project_target_type_for_legacy_tasks(
    client: TestClient, db_session: Session
) -> None:
    created_at = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        Project(
            id=2,
            name="legacy-backend-service",
            git_provider="GITLAB",
            git_project_id="2002",
            repository_url="https://gitlab.example.com/demo/legacy-backend",
            target_type="BACKEND",
            detected_target_types=None,
            target_detection_json=None,
            default_template_code="backend-default",
            default_code_quality_profile_code="backend-default-ai-review",
            default_code_quality_provider_code=None,
            dingtalk_webhook_id=None,
            status="ENABLED",
            description=None,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db_session.add(
        ReviewTask(
            id=10002,
            project_id=2,
            trigger_type="GITLAB_MR_WEBHOOK",
            external_source_id="13",
            external_url="https://gitlab.example.com/demo/legacy-backend/-/merge_requests/13",
            source_branch="feature/legacy",
            target_branch="main",
            commit_sha="abcdef654321",
            before_sha=None,
            after_sha=None,
            author_name="Alice",
            author_username="alice",
            template_code="backend-default",
            target_type=None,
            target_types_json=None,
            code_quality_profile_code=None,
            status="SUCCESS",
            risk_level="LOW",
            error_message=None,
            started_at=created_at,
            finished_at=created_at,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db_session.commit()

    backend_response = client.get("/api/review-tasks", params={"targetType": "BACKEND"})

    assert backend_response.status_code == 200
    backend_data = backend_response.json()["data"]
    assert backend_data["total"] == 1
    assert backend_data["items"][0]["id"] == 10002

    web_response = client.get("/api/review-tasks", params={"targetType": "WEB_PC"})

    assert web_response.status_code == 200
    assert web_response.json()["data"]["total"] == 0


def test_review_task_detail_not_found_uses_unified_error(client: TestClient) -> None:
    response = client.get("/api/review-tasks/404")

    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
