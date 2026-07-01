from __future__ import annotations

import json
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.project_integration.models import GitLabMergeRequestEvent, Project
from app.review_record.models import ReviewTask


def test_deterministic_checks_returns_explainable_empty_state(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_task(db_session, changed_files=[])

    response = client.get("/api/review-tasks/9001/deterministic-checks")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["taskId"] == 9001
    assert data["status"] == "NOT_RUN"
    assert data["latestRun"] is None
    assert "No deterministic check run" in data["explanation"]


def test_secret_scan_records_redacted_findings_from_added_diff_lines_only(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_task(
        db_session,
        changed_files=[
            {
                "path": "src/main/resources/application.yml",
                "diffText": (
                    "diff --git a/src/main/resources/application.yml b/src/main/resources/application.yml\n"
                    "@@ -10,4 +10,6 @@\n"
                    " spring:\n"
                    "-  password: deleted-secret-should-not-match\n"
                    "   datasource:\n"
                    "+    apiKey: sk-live-added-secret-token\n"
                    "+    url: jdbc:mysql://db/app?password=mysql-added-secret\n"
                    "+    Authorization: Bearer bearer-added-secret-token\n"
                ),
            },
            {
                "path": r"D:\private\repo\src\Key.java",
                "diffText": (
                    "@@ -1,1 +1,2 @@\n"
                    " class Key {}\n"
                    "+String marker = \"-----BEGIN PRIVATE KEY-----\";\n"
                ),
            },
        ],
    )

    response = client.post("/api/review-tasks/9001/deterministic-checks/run", json={})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "COMPLETED"
    assert data["checkType"] == "SECRET_SCAN"
    assert data["durationMs"] >= 0
    assert data["configSnapshot"]["configSource"] == "BUILTIN"
    assert data["configSnapshot"]["scope"] == "DIFF_ADDED_LINES"
    assert data["resultSummary"]["scannedFileCount"] == 2
    assert data["resultSummary"]["addedLineCount"] == 4
    assert data["resultSummary"]["findingCount"] == 4
    assert data["resultSummary"]["ruleTypeCounts"]["API_TOKEN_ASSIGNMENT"] == 1
    assert data["resultSummary"]["ruleTypeCounts"]["JDBC_OR_URL_PASSWORD"] == 1
    assert data["resultSummary"]["ruleTypeCounts"]["AUTHORIZATION_BEARER"] == 1
    assert data["resultSummary"]["ruleTypeCounts"]["PRIVATE_KEY_MARKER"] == 1
    assert {finding["filePath"] for finding in data["findings"]} == {
        "src/main/resources/application.yml",
        "Key.java",
    }
    payload = json.dumps(data, ensure_ascii=False)
    assert "sk-live-added-secret-token" not in payload
    assert "mysql-added-secret" not in payload
    assert "bearer-added-secret-token" not in payload
    assert "deleted-secret-should-not-match" not in payload
    assert r"D:\private\repo" not in payload
    assert "****" in payload

    listed = client.get("/api/review-tasks/9001/deterministic-checks")
    listed_data = listed.json()["data"]
    assert listed_data["status"] == "COMPLETED"
    assert listed_data["latestRun"]["id"] == data["id"]


def test_secret_scan_no_diff_is_not_applicable(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_task(
        db_session,
        changed_files=[{"path": "src/NoDiff.java", "diffText": ""}],
    )

    response = client.post("/api/review-tasks/9001/deterministic-checks/run", json={})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "NOT_APPLICABLE"
    assert data["resultSummary"]["findingCount"] == 0
    assert data["findings"] == []


def test_secret_scan_rejects_unsupported_check_type(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_task(db_session, changed_files=[])

    response = client.post("/api/review-tasks/9001/deterministic-checks/run", json={"checkType": "LINT"})

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def _seed_task(db_session: Session, *, changed_files: list[dict]) -> None:
    now = datetime.now()
    db_session.add(
        Project(
            id=9001,
            name="deterministic-demo-service",
            git_provider="GITLAB",
            git_project_id="git-9001",
            repository_url="https://gitlab.example.test/group/demo",
            default_template_code="backend-default",
            status="ENABLED",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        ReviewTask(
            id=9001,
            project_id=9001,
            trigger_type="GITLAB_MR_WEBHOOK",
            external_source_id="12",
            external_url="https://gitlab.example.test/group/demo/-/merge_requests/12",
            source_branch="feature/m6",
            target_branch="main",
            commit_sha="head-sha",
            template_code="backend-default",
            status="SUCCESS",
            review_status="NOT_TRIGGERED",
            risk_level="LOW",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        GitLabMergeRequestEvent(
            task_id=9001,
            git_project_id="git-9001",
            project_name="deterministic-demo-service",
            mr_id="12",
            event_action="open",
            source_branch="feature/m6",
            target_branch="main",
            changed_files_summary=json.dumps(
                {"count": len(changed_files), "source": "payload", "files": changed_files},
                ensure_ascii=False,
            ),
            raw_payload="{}",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
