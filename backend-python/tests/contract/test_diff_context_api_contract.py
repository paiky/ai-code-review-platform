from datetime import datetime
import json

import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.project_integration.models import GitLabPushEvent, Project
from app.review_record.models import ReviewTask


def seed_push_task(
    db_session: Session,
    *,
    task_id: int = 1,
    files: list[dict] | None = None,
    before_sha: str | None = "before-sha",
    after_sha: str | None = "after-sha",
) -> None:
    now = datetime(2026, 6, 2, 10, 0, 0)
    if db_session.get(Project, 1) is None:
        db_session.add(
            Project(
                id=1,
                name="demo-service",
                git_provider="GITLAB",
                git_project_id="1001",
                repository_url="https://gitlab.example.test/demo/service",
                default_template_code="backend-default",
                status="ENABLED",
                created_at=now,
                updated_at=now,
            )
        )
    changed_files = files or [
        {
            "path": "src/Foo Bar.java",
            "oldPath": "src/Foo Bar.java",
            "newPath": "src/Foo Bar.java",
            "changeType": "MODIFIED",
        }
    ]
    db_session.add(
        ReviewTask(
            id=task_id,
            project_id=1,
            trigger_type="GITLAB_PUSH_WEBHOOK",
            external_source_id=after_sha,
            source_branch="main",
            commit_sha=after_sha,
            before_sha=before_sha,
            after_sha=after_sha,
            template_code="backend-default",
            status="SUCCESS",
            review_status="NOT_TRIGGERED",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        GitLabPushEvent(
            task_id=task_id,
            git_project_id="1001",
            project_name="demo-service",
            ref="refs/heads/main",
            branch_name="main",
            before_sha=before_sha,
            after_sha=after_sha or "",
            changed_files_summary=json.dumps({"count": len(changed_files), "files": changed_files}),
            raw_payload="{}",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def enable_gitlab(monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_API_ENABLED", "true")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.test")
    monkeypatch.setenv("GITLAB_TOKEN", "unit-token")


def raw_file_route(path: str, ref: str):
    return respx.get(
        f"https://gitlab.example.test/api/v4/projects/1001/repository/files/{path}/raw",
        params={"ref": ref},
    )


@respx.mock
def test_diff_context_returns_push_left_and_right_sources(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    enable_gitlab(monkeypatch)
    seed_push_task(db_session)
    raw_file_route("src%2FFoo%20Bar.java", "before-sha").mock(return_value=httpx.Response(200, text="class Foo {\n}"))
    raw_file_route("src%2FFoo%20Bar.java", "after-sha").mock(return_value=httpx.Response(200, text="class Foo {\n  int value;\n}"))

    response = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/Foo Bar.java"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["language"] == "java"
    assert data["left"] == {"path": "src/Foo Bar.java", "ref": "before-sha", "lines": ["class Foo {", "}"]}
    assert data["right"] == {
        "path": "src/Foo Bar.java",
        "ref": "after-sha",
        "lines": ["class Foo {", "  int value;", "}"],
    }
    detail = client.get("/api/review-tasks/1").json()["data"]
    assert detail["diffContextCapabilities"] == {"diff": True, "fixPreview": True}


@respx.mock
def test_fix_preview_context_returns_current_source_as_left_baseline(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    enable_gitlab(monkeypatch)
    seed_push_task(db_session)
    raw_file_route("src%2FFoo%20Bar.java", "after-sha").mock(return_value=httpx.Response(200, text="class Foo {}"))

    response = client.get(
        "/api/review-tasks/1/diff-context",
        params={"filePath": "src/Foo Bar.java", "viewType": "FIX_PREVIEW"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["left"]["ref"] == "after-sha"
    assert response.json()["data"]["right"] is None


@respx.mock
def test_diff_context_handles_added_deleted_and_renamed_files(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    enable_gitlab(monkeypatch)
    seed_push_task(
        db_session,
        files=[
            {"path": "src/New.java", "newPath": "src/New.java", "newFile": True},
            {"path": "src/Old.java", "oldPath": "src/Old.java", "deletedFile": True},
            {"path": "src/NewName.java", "oldPath": "src/OldName.java", "newPath": "src/NewName.java", "renamedFile": True},
        ],
    )
    raw_file_route("src%2FNew.java", "after-sha").mock(return_value=httpx.Response(200, text="new"))
    raw_file_route("src%2FOld.java", "before-sha").mock(return_value=httpx.Response(200, text="old"))
    raw_file_route("src%2FOldName.java", "before-sha").mock(return_value=httpx.Response(200, text="before rename"))
    raw_file_route("src%2FNewName.java", "after-sha").mock(return_value=httpx.Response(200, text="after rename"))

    added = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/New.java"}).json()["data"]
    deleted = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/Old.java"}).json()["data"]
    renamed = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/NewName.java"}).json()["data"]

    assert added["left"] is None and added["right"]["lines"] == ["new"]
    assert deleted["left"]["lines"] == ["old"] and deleted["right"] is None
    assert renamed["left"]["path"] == "src/OldName.java"
    assert renamed["right"]["path"] == "src/NewName.java"


@respx.mock
def test_diff_context_supports_historical_change_type_only_file_summaries(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    enable_gitlab(monkeypatch)
    seed_push_task(
        db_session,
        files=[
            {"path": "src/New.java", "newPath": "src/New.java", "changeType": "ADDED"},
            {"path": "src/Old.java", "oldPath": "src/Old.java", "changeType": "DELETED"},
            {
                "path": "src/NewName.java",
                "oldPath": "src/OldName.java",
                "newPath": "src/NewName.java",
                "changeType": "RENAMED",
            },
        ],
    )
    raw_file_route("src%2FNew.java", "after-sha").mock(return_value=httpx.Response(200, text="new"))
    raw_file_route("src%2FOld.java", "before-sha").mock(return_value=httpx.Response(200, text="old"))
    raw_file_route("src%2FOldName.java", "before-sha").mock(return_value=httpx.Response(200, text="before rename"))
    raw_file_route("src%2FNewName.java", "after-sha").mock(return_value=httpx.Response(200, text="after rename"))

    added = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/New.java"}).json()["data"]
    deleted = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/Old.java"}).json()["data"]
    renamed = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/NewName.java"}).json()["data"]

    assert added["left"] is None and added["right"]["lines"] == ["new"]
    assert deleted["left"]["lines"] == ["old"] and deleted["right"] is None
    assert renamed["left"]["path"] == "src/OldName.java"
    assert renamed["right"]["path"] == "src/NewName.java"


def test_diff_context_rejects_file_outside_task_changes(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    enable_gitlab(monkeypatch)
    seed_push_task(db_session)

    response = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/Secret.java"})

    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


def test_diff_context_hides_capability_and_rejects_when_gitlab_api_is_disabled(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_push_task(db_session)

    detail = client.get("/api/review-tasks/1").json()["data"]
    response = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/Foo Bar.java"})

    assert detail["diffContextCapabilities"] == {"diff": False, "fixPreview": False}
    assert response.status_code == 400
    assert response.json()["message"] == "GitLab diff is not provided and GitLab API is disabled"


def test_diff_context_hides_capability_and_rejects_when_gitlab_token_is_missing(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GITLAB_API_ENABLED", "true")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.test")
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    seed_push_task(db_session)

    detail = client.get("/api/review-tasks/1").json()["data"]
    response = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/Foo Bar.java"})

    assert detail["diffContextCapabilities"] == {"diff": False, "fixPreview": False}
    assert response.status_code == 400
    assert response.json()["message"] == "GitLab API token is required"


def test_diff_context_rejects_missing_base_ref(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    enable_gitlab(monkeypatch)
    seed_push_task(db_session, before_sha=None)

    detail = client.get("/api/review-tasks/1").json()["data"]
    response = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/Foo Bar.java"})

    assert detail["diffContextCapabilities"] == {"diff": False, "fixPreview": True}
    assert response.status_code == 400
    assert response.json()["message"] == "Diff context base ref is unavailable for this task"


@respx.mock
def test_diff_context_returns_not_found_when_gitlab_raw_file_is_missing(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    enable_gitlab(monkeypatch)
    seed_push_task(db_session)
    raw_file_route("src%2FFoo%20Bar.java", "before-sha").mock(return_value=httpx.Response(404))

    response = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/Foo Bar.java"})

    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


@respx.mock
def test_diff_context_rejects_gitlab_raw_file_over_size_limit(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    enable_gitlab(monkeypatch)
    seed_push_task(db_session)
    raw_file_route("src%2FFoo%20Bar.java", "before-sha").mock(return_value=httpx.Response(200, content=b"x" * (1024 * 1024 + 1)))

    response = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/Foo Bar.java"})

    assert response.status_code == 400
    assert "exceeds 1048576 bytes" in response.json()["message"]


@respx.mock
def test_diff_context_rejects_gitlab_raw_file_over_line_limit(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    enable_gitlab(monkeypatch)
    seed_push_task(db_session)
    raw_file_route("src%2FFoo%20Bar.java", "before-sha").mock(return_value=httpx.Response(200, text="\n".join(["x"] * 20_001)))

    response = client.get("/api/review-tasks/1/diff-context", params={"filePath": "src/Foo Bar.java"})

    assert response.status_code == 400
    assert "exceeds 20000 lines" in response.json()["message"]
