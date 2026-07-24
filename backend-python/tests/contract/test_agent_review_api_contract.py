from __future__ import annotations

from datetime import datetime, timedelta
import json

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent_review.models import AgentReviewSettings
from app.agent_review.repository import create_agent_job, expire_exhausted_agent_jobs
from app.code_quality.models import CodeQualitySchedulerJob
from app.code_quality.repository import list_result_responses, save_result
from app.project_integration.models import Project, ProjectGroup
from app.review_record.models import ReviewTask


def _configure(monkeypatch) -> tuple[str, str]:
    encryption_key = Fernet.generate_key().decode("ascii")
    worker_token = "worker-token-for-agent-review-tests"
    monkeypatch.setenv("AGENT_REVIEW_CONFIG_ENCRYPTION_KEY", encryption_key)
    monkeypatch.setenv("AGENT_REVIEW_WORKER_TOKEN", worker_token)
    return encryption_key, worker_token


def _worker_headers(token: str) -> dict[str, str]:
    return {"X-Agent-Worker-Token": token}


def test_agent_settings_encrypt_mask_replace_and_clear(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _configure(monkeypatch)

    saved = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "sk-agent-secret-123456"},
    )

    assert saved.status_code == 200
    data = saved.json()["data"]
    assert data["apiKeyConfigured"] is True
    assert data["apiKeyMasked"].startswith("configured:")
    assert "sk-agent-secret-123456" not in saved.text
    record = db_session.get(AgentReviewSettings, 1)
    assert record.api_key_ciphertext != "sk-agent-secret-123456"
    assert "sk-agent-secret-123456" not in record.api_key_ciphertext

    kept = client.put("/api/code-quality-reviews/agent-settings", json={"enabled": True})
    assert kept.status_code == 200
    assert db_session.get(AgentReviewSettings, 1).api_key_ciphertext == record.api_key_ciphertext

    cleared = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"clearApiKey": True, "enabled": False},
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["apiKeyConfigured"] is False
    assert cleared.json()["data"]["enabled"] is False


def test_agent_key_save_is_rejected_without_master_key(client: TestClient) -> None:
    response = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "sk-agent-secret"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "AGENT_ENCRYPTION_KEY_UNAVAILABLE"
    assert "sk-agent-secret" not in response.text


def test_project_group_requires_explicit_source_export_consent(client: TestClient) -> None:
    rejected = client.post(
        "/api/project-groups",
        json={"groupName": "Agent 项目", "groupCode": "agent", "reviewEngine": "AGENT"},
    )
    assert rejected.status_code == 400

    accepted = client.post(
        "/api/project-groups",
        json={
            "groupName": "Agent 项目",
            "groupCode": "agent",
            "reviewEngine": "AGENT",
            "agentSourceExportAllowed": True,
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["reviewEngine"] == "AGENT"
    assert accepted.json()["data"]["agentSourceExportAllowed"] is True


def test_agent_configuration_test_runs_through_worker_contract(
    client: TestClient, monkeypatch
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "sk-agent-secret-123456"},
    )
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={"workerId": "worker-1"},
    )

    requested = client.post("/api/code-quality-reviews/agent-settings/test")
    assert requested.status_code == 200
    assert requested.json()["data"]["status"] == "QUEUED"
    claimed = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-1"},
    )
    job = claimed.json()["data"]
    assert job["kind"] == "CONFIG_TEST"
    assert job["apiKey"] == "sk-agent-secret-123456"
    completed = client.post(
        "/internal/agent-review/configuration-test/complete",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-1",
            "requestId": job["requestId"],
            "status": "SUCCESS",
            "message": "ok",
            "durationMs": 123,
        },
    )
    assert completed.status_code == 200
    assert completed.json()["data"]["status"] == "SUCCESS"
    settings = client.get("/api/code-quality-reviews/agent-settings").json()["data"]
    assert settings["configurationTest"]["status"] == "SUCCESS"


def test_worker_auth_claim_and_heartbeat(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "sk-agent-secret-123456"},
    )
    unauthorized = client.post(
        "/internal/agent-review/workers/heartbeat", json={"workerId": "worker-1"}
    )
    assert unauthorized.status_code == 401
    heartbeat = client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={"workerId": "worker-1", "workerVersion": "test", "cliVersion": "2.1.112"},
    )
    assert heartbeat.status_code == 200

    now = datetime.now()
    group = ProjectGroup(
        id=10,
        group_name="Agent",
        group_code="agent",
        review_engine="AGENT",
        agent_source_export_allowed=True,
        status="ENABLED",
        created_at=now,
        updated_at=now,
    )
    db_session.add(group)
    db_session.flush()
    run = create_agent_job(
        db_session,
        task_id=99,
        project_id=100,
        input_payload={
            "worktree": "worktrees/99/head",
            "case": {
                "id": "task-99",
                "changedFiles": ["src/a.py"],
                "diff": "+dangerous()",
            },
        },
        completion_context={},
        comparison_mode=True,
    )
    db_session.commit()

    claim = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-1"},
    )
    assert claim.status_code == 200
    job = claim.json()["data"]
    assert job["runId"] == run.id
    assert job["apiKey"] == "sk-agent-secret-123456"
    assert "apiKey" not in json.dumps(job["input"])

    job_heartbeat = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/heartbeat",
        headers=_worker_headers(token),
        json={"workerId": "worker-1", "runSummary": {"toolCallCount": 3}},
    )
    assert job_heartbeat.status_code == 200
    assert job_heartbeat.json()["data"]["cancelRequested"] is False

    # Completion validation is exercised separately with a real ReviewTask/result row;
    # the claim contract itself must never persist or echo the clear key outside this response.
    settings_record = db_session.get(AgentReviewSettings, 1)
    assert "sk-agent-secret-123456" not in settings_record.api_key_ciphertext


def test_worker_completion_is_idempotent_and_saves_engine_metadata(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "sk-agent-secret-123456"},
    )
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={"workerId": "worker-1", "workerVersion": "test", "cliVersion": "2.1.112"},
    )
    now = datetime.now()
    db_session.add(
        ReviewTask(
            id=199,
            project_id=100,
            trigger_type="CODE_QUALITY_MANUAL",
            template_code="backend-default",
            target_type="BACKEND",
            code_quality_profile_code="backend-default-ai-review",
            status="SUCCESS",
            review_status="RUNNING",
            created_at=now,
            updated_at=now,
        )
    )
    run = create_agent_job(
        db_session,
        task_id=199,
        project_id=100,
        input_payload={
            "worktree": "worktrees/199/head",
            "case": {"id": "task-199", "changedFiles": ["src/a.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=True,
    )
    db_session.commit()
    job = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-1"},
    ).json()["data"]
    payload = {
        "workerId": "worker-1",
        "idempotencyKey": job["idempotencyKey"],
        "reviewCard": {"summary": "未发现问题", "overallLevel": "LOW", "findings": []},
        "runSummary": {"durationMs": 1200, "numTurns": 2, "toolCallCount": 4},
    }

    first = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/complete",
        headers=_worker_headers(token),
        json=payload,
    )
    second = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/complete",
        headers=_worker_headers(token),
        json=payload,
    )

    assert first.status_code == 200
    assert first.json()["data"]["idempotent"] is False
    assert second.status_code == 200
    assert second.json()["data"]["idempotent"] is True
    result = list_result_responses(db_session, 199)[0]
    assert result["requestedEngine"] == "AGENT"
    assert result["effectiveEngine"] == "AGENT"
    assert result["agentRunSummary"]["runId"] == run.id


def test_worker_failure_records_explicit_standard_fallback(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    scheduled: list[int] = []
    monkeypatch.setattr(
        "app.code_quality.service.schedule_agent_standard_fallback",
        lambda _db, run_id: scheduled.append(run_id),
    )
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "sk-agent-secret-123456"},
    )
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={"workerId": "worker-1"},
    )
    run = create_agent_job(
        db_session,
        task_id=299,
        project_id=100,
        input_payload={"worktree": "worktrees/299/head", "case": {"changedFiles": ["src/a.py"], "diff": "+x"}},
        completion_context={},
        comparison_mode=False,
    )
    db_session.commit()
    job = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-1"},
    ).json()["data"]

    failed = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/fail",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-1",
            "idempotencyKey": job["idempotencyKey"],
            "failureCode": "AGENT_TIMEOUT",
            "failureMessage": "timeout",
            "runSummary": {"durationMs": 600000},
        },
    )

    assert failed.status_code == 200
    db_session.refresh(run)
    assert run.status == "TIMED_OUT"
    assert run.effective_engine == "STANDARD_FALLBACK"
    assert scheduled == [run.id]
    assert run.input_json is not None


def test_offline_worker_queue_grace_expires_to_explicit_fallback(db_session: Session) -> None:
    run = create_agent_job(
        db_session,
        task_id=300,
        project_id=100,
        input_payload={"worktree": "worktrees/300/head", "case": {"changedFiles": ["src/a.py"]}},
        completion_context={},
        comparison_mode=False,
    )
    job = db_session.get(CodeQualitySchedulerJob, run.scheduler_job_id)
    assert job is not None
    job.queued_at = datetime.now() - timedelta(seconds=61)
    db_session.commit()

    expired = expire_exhausted_agent_jobs(db_session)
    db_session.commit()

    db_session.refresh(run)
    assert expired == [run.id]
    assert run.status == "FAILED"
    assert run.effective_engine == "STANDARD_FALLBACK"
    assert run.failure_code == "AGENT_LEASE_EXHAUSTED"


def test_running_agent_job_cancel_is_observed_by_worker_and_clears_input(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "sk-agent-secret-123456"},
    )
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={"workerId": "worker-cancel"},
    )
    run = create_agent_job(
        db_session,
        task_id=302,
        project_id=100,
        input_payload={"worktree": "worktrees/302/head", "case": {"changedFiles": ["src/a.py"]}},
        completion_context={},
        comparison_mode=True,
    )
    db_session.commit()
    job = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-cancel"},
    ).json()["data"]

    cancelled = client.post(
        "/api/code-quality-reviews/tasks/302/cancel",
        json={"jobType": "AGENT_REVIEW", "reviewKey": job["reviewKey"]},
    )
    assert cancelled.status_code == 404  # No ReviewTask exists yet; task boundary is enforced.

    now = datetime.now()
    db_session.add(
        ReviewTask(
            id=302,
            project_id=100,
            trigger_type="GITLAB_MR_WEBHOOK",
            template_code="backend-default",
            target_type="BACKEND",
            code_quality_profile_code="backend-default-ai-review",
            status="SUCCESS",
            review_status="RUNNING",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    cancelled = client.post(
        "/api/code-quality-reviews/tasks/302/cancel",
        json={"jobType": "AGENT_REVIEW", "reviewKey": job["reviewKey"]},
    )
    assert cancelled.status_code == 200
    heartbeat = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/heartbeat",
        headers=_worker_headers(token),
        json={"workerId": "worker-cancel"},
    )
    assert heartbeat.json()["data"]["cancelRequested"] is True
    acknowledged = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/cancelled",
        headers=_worker_headers(token),
        json={"workerId": "worker-cancel", "idempotencyKey": job["idempotencyKey"]},
    )
    assert acknowledged.status_code == 200
    db_session.refresh(run)
    assert run.status == "CANCELLED"
    assert run.failure_code == "AGENT_CANCELLED"
    assert run.input_json is None


def test_manual_agent_review_reaches_persistent_worker_queue(
    client: TestClient, db_session: Session, monkeypatch, tmp_path
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    workspace = tmp_path / "worktrees" / "301" / "head"
    workspace.mkdir(parents=True)
    (workspace / "service.py").write_text("value = None\n", encoding="utf-8")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.agent_review.service._ensure_worktree", lambda _task, _project: workspace)
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "sk-agent-secret-123456"},
    )
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={"workerId": "worker-1"},
    )
    now = datetime.now()
    group = ProjectGroup(
        id=30,
        group_name="Agent 项目组",
        group_code="agent-manual",
        default_code_quality_profile_code="backend-default-ai-review",
        review_engine="AGENT",
        agent_source_export_allowed=True,
        ai_review_enabled=True,
        trigger_on_manual=True,
        status="ENABLED",
        created_at=now,
        updated_at=now,
    )
    project = Project(
        id=301,
        group_id=30,
        name="agent-demo",
        git_provider="GITLAB",
        git_project_id="301",
        repository_url="https://gitlab.example.com/demo/agent",
        default_template_code="backend-default",
        default_code_quality_profile_code="backend-default-ai-review",
        status="ENABLED",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([group, project])
    db_session.commit()

    response = client.post(
        "/api/code-quality-reviews/manual",
        json={
            "projectId": 301,
            "profileCode": "backend-default-ai-review",
            "reviewEngine": "AGENT",
            "mode": "DIFF_TEXT",
            "commitSha": "a" * 40,
            "title": "Agent manual validation",
            "diffText": "diff --git a/service.py b/service.py\n+++ b/service.py\n+value = None",
            "changedFiles": ["service.py"],
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["requestedEngine"] == "AGENT"
    assert data["effectiveEngine"] == "AGENT"
    claimed = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-1"},
    )
    assert claimed.status_code == 200
    job = claimed.json()["data"]
    assert job["input"]["changedFiles"] == ["service.py"]
    completed = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/complete",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-1",
            "idempotencyKey": job["idempotencyKey"],
            "reviewCard": {"summary": "未发现问题", "overallLevel": "LOW", "findings": []},
            "runSummary": {"durationMs": 800, "numTurns": 2, "toolCallCount": 3},
        },
    )
    assert completed.status_code == 200
    results = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-results")
    assert results.status_code == 200
    saved = results.json()["data"][0]
    assert saved["status"] == "SUCCESS"
    assert saved["effectiveEngine"] == "AGENT"


def test_webhook_task_can_append_agent_comparison_without_overwriting_standard(
    client: TestClient, db_session: Session, monkeypatch, tmp_path
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    workspace = tmp_path / "worktrees" / "401" / "head"
    workspace.mkdir(parents=True)
    (workspace / "service.py").write_text("value = None\n", encoding="utf-8")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.agent_review.service._ensure_worktree", lambda _task, _project: workspace)
    monkeypatch.setattr(
        "app.code_quality.service._request_from_task_event",
        lambda _db, _task, _profile: {
            "mode": "DIFF_TEXT",
            "commitSha": "b" * 40,
            "title": "Agent comparison",
            "diffText": "diff --git a/service.py b/service.py\n+++ b/service.py\n+value = None",
            "changedFiles": ["service.py"],
        },
    )
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "sk-agent-secret-123456"},
    )
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={"workerId": "worker-comparison"},
    )
    now = datetime.now()
    group = ProjectGroup(
        id=40,
        group_name="Agent 对照项目组",
        group_code="agent-comparison",
        default_code_quality_profile_code="backend-default-ai-review",
        review_engine="STANDARD",
        agent_source_export_allowed=True,
        ai_review_enabled=True,
        status="ENABLED",
        created_at=now,
        updated_at=now,
    )
    project = Project(
        id=401,
        group_id=40,
        name="agent-comparison-demo",
        git_provider="GITLAB",
        git_project_id="401",
        repository_url="https://gitlab.example.com/demo/agent-comparison",
        default_template_code="backend-default",
        default_code_quality_profile_code="backend-default-ai-review",
        status="ENABLED",
        created_at=now,
        updated_at=now,
    )
    task = ReviewTask(
        id=401,
        project_id=401,
        trigger_type="GITLAB_MR_WEBHOOK",
        template_code="backend-default",
        target_type="BACKEND",
        code_quality_profile_code="backend-default-ai-review",
        status="SUCCESS",
        review_status="SUCCESS",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([group, project, task])
    db_session.flush()
    save_result(
        db_session,
        task_id=401,
        review_key="standard-deepseek",
        project_id=401,
        profile_code="backend-default-ai-review",
        provider="DEEPSEEK",
        model="deepseek-v4-pro",
        display_name="普通 Review",
        sort_order=10,
        result={
            "status": "SUCCESS",
            "overallLevel": "LOW",
            "summary": "普通 Review 已完成",
            "findings": [],
            "requestedEngine": "STANDARD",
            "effectiveEngine": "STANDARD",
        },
    )
    db_session.commit()

    response = client.post(
        "/api/code-quality-reviews/tasks/401/retry",
        json={"reviewEngine": "AGENT", "comparisonMode": True},
    )

    assert response.status_code == 200, response.text
    reviews = client.get("/api/review-tasks/401/code-quality-results").json()["data"]
    assert {(item["reviewKey"], item["requestedEngine"]) for item in reviews} == {
        ("standard-deepseek", "STANDARD"),
        ("agent-claude-code-deepseek-v4-pro", "AGENT"),
    }
