from __future__ import annotations

from datetime import datetime, timedelta
import json

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.agent_review import repository as agent_repository
from app.agent_review.models import AgentReviewRun, AgentReviewSettings, AgentReviewWorker
from app.agent_review.repository import (
    cleanup_stale_agent_workers,
    create_agent_job,
    expire_exhausted_agent_jobs,
    sanitize_agent_audit,
)
from app.agent_review.service import _ensure_worktree
from app.agent_review_spike.budgets import default_agent_budgets
from app.code_quality.models import CodeQualitySchedulerJob
from app.code_quality.repository import list_progress, list_result_responses, save_result
from app.code_quality.service import (
    _agent_preflight_fallback_metadata,
    schedule_agent_standard_fallback,
)
from app.core.errors import AppError
from app.core.json_utils import utc_now
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


def _trace_audit(events):
    last_budget = (
        events[-1].get("reviewBudget")
        if events and isinstance(events[-1], dict)
        else {
            "phase": "DISCOVERY",
            "evidenceCallsUsed": 0,
            "evidenceCallsRemaining": 10,
            "sourceBytesRemaining": 200_000,
            "mustSubmit": False,
        }
    )
    return {
        "phase": "SUBMITTING" if last_budget.get("phase") == "SUBMIT" else "TOOL_ACTIVITY",
        "toolCallCount": len(events),
        "evidenceCallsUsed": last_budget.get("evidenceCallsUsed", 0),
        "sourceBytesReturned": sum(int(item.get("sourceBytes") or 0) for item in events),
        "diffBytesReturned": 0,
        "blockedAccessCount": 0,
        "reviewSubmitted": bool(events and events[-1].get("tool") == "submit_review"),
        "reviewBudget": last_budget,
        "topPathSummaries": [],
        "events": events,
    }


def test_backend_agent_audit_whitelist_caps_events_and_drops_raw_content() -> None:
    budget = {
        "phase": "DISCOVERY",
        "evidenceCallsUsed": 1,
        "evidenceCallsRemaining": 9,
        "sourceBytesRemaining": 199_900,
        "mustSubmit": False,
    }
    events = [
        {
            "sequence": sequence,
            "tool": "search_code",
            "status": "SUCCESS",
            "durationMs": 1,
            "itemCount": 1,
            "sourceBytes": 1,
            "pathSummary": [],
            "reviewBudget": budget,
            "query": "SECRET_QUERY",
            "source": "SECRET_SOURCE",
            "assistant": "SECRET_ASSISTANT",
            "reasoning": "SECRET_REASONING",
            "path": "D:/private/source.py",
        }
        for sequence in range(1, 62)
    ]

    safe = sanitize_agent_audit(_trace_audit(events))
    text = json.dumps(safe, ensure_ascii=False)

    assert len(safe["events"]) == 60
    assert "SECRET_" not in text
    assert "D:/private" not in text
    assert '"query"' not in text


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
    assert data["budgets"]["maxTurns"] == 12
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


def test_agent_settings_update_and_reset_runtime_budgets(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _configure(monkeypatch)

    initial = client.get("/api/code-quality-reviews/agent-settings")
    assert initial.status_code == 200
    initial_data = initial.json()["data"]
    assert initial_data["budgetConfigSource"] == "DEFAULT"
    assert initial_data["budgets"]["maxEvidenceCalls"] == 10
    assert initial_data["budgetDefaults"]["maxTurns"] == 12
    assert initial_data["budgetLimits"]["maxTurns"] == {"min": 6, "max": 18}

    updated = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={
            "enabled": True,
            "apiKey": "sk-agent-secret-123456",
            "budgets": {"maxTurns": 14},
        },
    )
    assert updated.status_code == 200
    updated_data = updated.json()["data"]
    assert updated_data["budgetConfigSource"] == "CUSTOM"
    assert updated_data["budgets"]["maxTurns"] == 14
    assert updated_data["budgets"]["maxEvidenceCalls"] == 10
    assert "sk-agent-secret-123456" not in updated.text
    db_session.expire_all()
    stored = json.loads(db_session.get(AgentReviewSettings, 1).budget_config_json)
    assert set(stored) == set(default_agent_budgets())

    full_budgets = {
        "maxTurns": 18,
        "maxToolCalls": 60,
        "maxSourceBytes": 300_000,
        "timeoutSeconds": 900,
        "inlineDiffBytes": 300_000,
        "maxEvidenceCalls": 15,
        "convergeAtCalls": 13,
        "submitByTurn": 15,
    }
    full_update = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"budgets": full_budgets},
    )
    assert full_update.status_code == 200
    assert {
        key: full_update.json()["data"]["budgets"][key] for key in full_budgets
    } == full_budgets
    assert full_update.json()["data"]["apiKeyConfigured"] is True

    reset = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"resetBudgets": True},
    )
    assert reset.status_code == 200
    assert reset.json()["data"]["budgetConfigSource"] == "DEFAULT"
    assert reset.json()["data"]["budgets"]["maxTurns"] == 12
    db_session.expire_all()
    assert db_session.get(AgentReviewSettings, 1).budget_config_json is None


@pytest.mark.parametrize(
    "budgets",
    [
        {"maxTurns": True},
        {"maxTurns": "14"},
        {"maxTurns": 14.0},
        {"maxTurns": None},
        {"unknown": 1},
        {"maxTurns": 19},
        {"maxEvidenceCalls": 10, "convergeAtCalls": 9},
        {"maxTurns": 12, "submitByTurn": 10},
        {"maxToolCalls": 10, "maxEvidenceCalls": 10},
    ],
)
def test_agent_settings_reject_invalid_runtime_budgets(
    client: TestClient, budgets: dict[str, object]
) -> None:
    response = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"budgets": budgets},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_agent_settings_reject_budget_update_and_reset_together(
    client: TestClient,
) -> None:
    response = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"budgets": {"maxTurns": 14}, "resetBudgets": True},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    false_conflict = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"budgets": {"maxTurns": 14}, "resetBudgets": False},
    )
    assert false_conflict.status_code == 400
    invalid_type = client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"resetBudgets": "true"},
    )
    assert invalid_type.status_code == 400


def test_agent_settings_corrupt_stored_budget_falls_back_to_defaults(
    client: TestClient, db_session: Session
) -> None:
    client.get("/api/code-quality-reviews/agent-settings")
    record = db_session.get(AgentReviewSettings, 1)
    record.budget_config_json = "not-json"
    db_session.commit()

    response = client.get("/api/code-quality-reviews/agent-settings")

    assert response.status_code == 200
    assert response.json()["data"]["budgetConfigSource"] == "DEFAULT"
    assert response.json()["data"]["budgets"]["maxTurns"] == 12
    record.budget_config_json = '{"maxTurns": 18}'
    db_session.commit()
    partial = client.get("/api/code-quality-reviews/agent-settings")
    assert partial.json()["data"]["budgetConfigSource"] == "DEFAULT"


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
        json={
            "enabled": True,
            "apiKey": "sk-agent-secret-123456",
            "budgets": {"maxTurns": 14},
        },
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
    assert job["budgets"]["maxTurns"] == 4
    duplicate_claim = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-2"},
    )
    assert duplicate_claim.status_code == 200
    assert duplicate_claim.json()["data"] is None
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


def test_worker_pool_registers_state_capacity_and_safe_activity(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _encryption_key, token = _configure(monkeypatch)

    first = client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "agent-worker-a",
            "workerVersion": "worker-v2",
            "cliVersion": "2.1.112",
            "state": "IDLE",
            "capacity": 1,
            "rawSource": "SECRET_SOURCE",
        },
    )
    second = client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "agent-worker-b",
            "workerVersion": "worker-v2",
            "cliVersion": "2.1.112",
            "state": "BUSY",
            "capacity": 1,
            "activeJobId": 81,
            "activeRunId": 91,
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    settings = client.get("/api/code-quality-reviews/agent-settings").json()["data"]
    pool = settings["workerPool"]
    assert settings["workerStatus"] == "ONLINE"
    assert settings["workerId"] == "agent-worker-b"
    assert pool["status"] == "ONLINE"
    assert pool["onlineCount"] == 2
    assert pool["busyCount"] == 1
    assert pool["idleCount"] == 1
    assert pool["totalCapacity"] == 2
    nodes = {node["workerId"]: node for node in pool["nodes"]}
    assert nodes["agent-worker-a"]["state"] == "IDLE"
    assert nodes["agent-worker-b"]["activeJobId"] == 81
    assert nodes["agent-worker-b"]["activeRunId"] == 91
    assert set(nodes["agent-worker-b"]) == {
        "workerId",
        "workerVersion",
        "cliVersion",
        "state",
        "capacity",
        "activeJobId",
        "activeRunId",
        "startedAt",
        "lastHeartbeatAt",
        "online",
    }
    assert "SECRET_SOURCE" not in json.dumps(pool, ensure_ascii=False)
    assert db_session.get(AgentReviewWorker, "agent-worker-b").capacity == 1


def test_worker_pool_tracks_state_transitions_offline_and_retention_cleanup(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "agent-worker-state",
            "state": "BUSY",
            "capacity": 1,
            "activeJobId": 17,
            "activeRunId": 27,
        },
    )
    busy_settings = client.get(
        "/api/code-quality-reviews/agent-settings"
    ).json()["data"]
    assert busy_settings["workerStatus"] == "ONLINE"
    assert busy_settings["workerPool"]["busyCount"] == 1
    assert busy_settings["workerPool"]["idleCount"] == 0
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "agent-worker-state",
            "state": "IDLE",
            "capacity": 1,
        },
    )
    worker_record = db_session.get(AgentReviewWorker, "agent-worker-state")
    assert worker_record.state == "IDLE"
    assert worker_record.active_job_id is None
    assert worker_record.active_run_id is None

    worker_record.last_heartbeat_at = utc_now() - timedelta(seconds=61)
    db_session.commit()
    offline_pool = client.get(
        "/api/code-quality-reviews/agent-settings"
    ).json()["data"]["workerPool"]
    assert offline_pool["onlineCount"] == 0
    assert offline_pool["nodes"][0]["online"] is False

    cleanup_now = utc_now()
    worker_record.last_heartbeat_at = cleanup_now - timedelta(
        hours=47, minutes=59
    )
    db_session.commit()
    assert cleanup_stale_agent_workers(db_session, now=cleanup_now) == 0
    assert db_session.get(AgentReviewWorker, "agent-worker-state") is not None

    worker_record.last_heartbeat_at = cleanup_now - timedelta(
        hours=48, seconds=1
    )
    db_session.commit()
    assert cleanup_stale_agent_workers(db_session, now=cleanup_now) == 1
    db_session.commit()
    assert db_session.get(AgentReviewWorker, "agent-worker-state") is None


@pytest.mark.parametrize(
    "payload",
    [
        {"workerId": "worker/unsafe"},
        {"workerId": 123},
        {"workerId": "worker-1", "state": "UNKNOWN"},
        {"workerId": "worker-1", "state": False},
        {"workerId": "worker-1", "capacity": True},
        {"workerId": "worker-1", "capacity": 2},
        {"workerId": "worker-1", "activeJobId": "1", "state": "BUSY"},
        {
            "workerId": "worker-1",
            "activeJobId": 9_223_372_036_854_775_808,
            "state": "BUSY",
        },
        {"workerId": "worker-1", "activeRunId": False, "state": "BUSY"},
        {"workerId": "worker-1", "activeJobId": 1, "state": "IDLE"},
    ],
)
def test_worker_pool_rejects_invalid_registration_payloads(
    client: TestClient, monkeypatch, payload
) -> None:
    _encryption_key, token = _configure(monkeypatch)

    response = client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_worker_pool_keeps_legacy_singleton_status_compatible(
    client: TestClient, db_session: Session
) -> None:
    client.get("/api/code-quality-reviews/agent-settings")
    settings_record = db_session.get(AgentReviewSettings, 1)
    settings_record.worker_id = "legacy-worker-1"
    settings_record.worker_version = "legacy"
    settings_record.last_worker_heartbeat_at = utc_now()
    db_session.commit()

    data = client.get("/api/code-quality-reviews/agent-settings").json()["data"]

    assert data["workerStatus"] == "ONLINE"
    assert data["workerId"] == "legacy-worker-1"
    assert data["workerPool"]["onlineCount"] == 1
    assert data["workerPool"]["totalCapacity"] == 1
    assert data["workerPool"]["nodes"][0]["workerId"] == "legacy-worker-1"


def test_worker_pool_schema_contains_registration_columns_and_heartbeat_index(
    db_session: Session,
) -> None:
    inspector = inspect(db_session.get_bind())
    columns = {
        column["name"]
        for column in inspector.get_columns("code_quality_agent_workers")
    }
    indexes = {
        index["name"]
        for index in inspector.get_indexes("code_quality_agent_workers")
    }

    assert columns == {
        "worker_id",
        "worker_version",
        "cli_version",
        "state",
        "capacity",
        "active_job_id",
        "active_run_id",
        "started_at",
        "last_heartbeat_at",
        "updated_at",
    }
    assert "idx_code_quality_agent_workers_heartbeat" in indexes


def test_agent_queue_metrics_empty_queue_and_zero_capacity(
    client: TestClient,
) -> None:
    data = client.get("/api/code-quality-reviews/agent-settings").json()["data"]
    metrics = data["queueMetrics"]

    assert metrics == {
        "queued": 0,
        "running": 0,
        "expiredLease": 0,
        "oldestQueuedSeconds": 0,
        "onlineCapacity": 0,
        "busyCapacity": 0,
        "utilizationPercent": 0,
        "drainingWorkers": 0,
        "lastWorkerHeartbeatAt": None,
    }


def test_agent_queue_metrics_aggregate_jobs_capacity_and_safe_whitelist(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    now = utc_now()
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "agent-worker-busy",
            "state": "BUSY",
            "capacity": 1,
            "activeJobId": 81,
            "activeRunId": 91,
        },
    )
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "agent-worker-draining",
            "state": "DRAINING",
            "capacity": 1,
        },
    )
    db_session.add_all(
        [
            CodeQualitySchedulerJob(
                job_type="AGENT_REVIEW",
                task_id=701,
                status="QUEUED",
                priority=80,
                queued_at=now - timedelta(seconds=125),
            ),
            CodeQualitySchedulerJob(
                job_type="AGENT_REVIEW",
                task_id=702,
                status="QUEUED",
                priority=80,
                queued_at=now,
            ),
            CodeQualitySchedulerJob(
                job_type="AGENT_REVIEW",
                task_id=703,
                status="RUNNING",
                priority=80,
                lease_expires_at=now + timedelta(seconds=30),
                queued_at=now - timedelta(seconds=10),
            ),
            CodeQualitySchedulerJob(
                job_type="AGENT_REVIEW",
                task_id=704,
                status="RUNNING",
                priority=80,
                lease_expires_at=now - timedelta(seconds=1),
                queued_at=now - timedelta(seconds=20),
            ),
            CodeQualitySchedulerJob(
                job_type="STANDARD_REVIEW",
                task_id=705,
                status="QUEUED",
                priority=100,
                queued_at=now - timedelta(hours=1),
            ),
        ]
    )
    db_session.commit()

    data = client.get("/api/code-quality-reviews/agent-settings").json()["data"]
    metrics = data["queueMetrics"]

    assert set(metrics) == {
        "queued",
        "running",
        "expiredLease",
        "oldestQueuedSeconds",
        "onlineCapacity",
        "busyCapacity",
        "utilizationPercent",
        "drainingWorkers",
        "lastWorkerHeartbeatAt",
    }
    assert metrics["queued"] == 2
    assert metrics["running"] == 2
    assert metrics["expiredLease"] == 1
    assert 125 <= metrics["oldestQueuedSeconds"] <= 130
    assert metrics["onlineCapacity"] == 1
    assert metrics["busyCapacity"] == 1
    assert metrics["utilizationPercent"] == 100
    assert metrics["drainingWorkers"] == 1
    assert isinstance(metrics["lastWorkerHeartbeatAt"], str)
    assert all(
        type(metrics[key]) is int and metrics[key] >= 0
        for key in set(metrics) - {"lastWorkerHeartbeatAt"}
    )
    assert data["workerPool"]["onlineCapacity"] == 1
    assert data["workerPool"]["busyCapacity"] == 1
    assert data["workerPool"]["utilizationPercent"] == 100
    assert data["workerPool"]["lastHeartbeatAt"] == metrics["lastWorkerHeartbeatAt"]


def test_agent_queue_metrics_historical_damage_and_observation_failure_are_safe(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    now = utc_now()
    db_session.add(
        CodeQualitySchedulerJob(
            job_type="AGENT_REVIEW",
            task_id=711,
            status="QUEUED",
            priority=80,
            queued_at=None,
        )
    )
    db_session.add(
        AgentReviewWorker(
            worker_id="historical-worker",
            state="DAMAGED",
            capacity=-9,
            started_at=now,
            last_heartbeat_at=now,
            updated_at=now,
        )
    )
    db_session.commit()

    historical = client.get("/api/code-quality-reviews/agent-settings").json()["data"]
    assert historical["queueMetrics"]["queued"] == 1
    assert historical["queueMetrics"]["oldestQueuedSeconds"] == 0
    assert historical["queueMetrics"]["onlineCapacity"] == 1
    assert historical["workerPool"]["nodes"][0]["state"] == "IDLE"
    assert historical["workerPool"]["nodes"][0]["capacity"] == 1

    monkeypatch.setattr(
        agent_repository,
        "agent_queue_metrics",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("unsafe raw detail")),
    )
    fallback = client.get("/api/code-quality-reviews/agent-settings")
    assert fallback.status_code == 200
    fallback_data = fallback.json()["data"]
    assert fallback_data["workerStatus"] == "ONLINE"
    assert fallback_data["queueMetrics"]["queued"] == 0
    assert fallback_data["queueMetrics"]["onlineCapacity"] == 1
    assert "unsafe raw detail" not in fallback.text


def test_all_online_workers_busy_keep_old_agent_job_queued_without_fallback(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "test-agent-key-queue-governance"},
    )
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "agent-worker-busy",
            "state": "BUSY",
            "capacity": 1,
            "activeJobId": 801,
            "activeRunId": 901,
        },
    )
    run = create_agent_job(
        db_session,
        task_id=712,
        project_id=100,
        input_payload={
            "worktree": "worktrees/712/head",
            "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=False,
    )
    job = db_session.get(CodeQualitySchedulerJob, run.scheduler_job_id)
    job.queued_at = utc_now() - timedelta(seconds=61)
    db_session.commit()

    assert agent_repository.assert_agent_available(
        db_session,
        require_worker=True,
    ) is not None
    assert expire_exhausted_agent_jobs(db_session) == []
    db_session.commit()
    db_session.refresh(job)
    db_session.refresh(run)

    assert job.status == "QUEUED"
    assert run.status == "PENDING"
    assert run.effective_engine is None
    data = client.get("/api/code-quality-reviews/agent-settings").json()["data"]
    assert data["workerStatus"] == "ONLINE"
    assert data["queueMetrics"]["queued"] == 1
    assert data["queueMetrics"]["onlineCapacity"] == 1
    assert data["queueMetrics"]["busyCapacity"] == 1


def test_draining_worker_cannot_claim_and_other_worker_can_take_job(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "test-agent-key-queue-governance"},
    )
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "agent-worker-draining",
            "state": "DRAINING",
            "capacity": 1,
        },
    )
    run = create_agent_job(
        db_session,
        task_id=713,
        project_id=100,
        input_payload={
            "worktree": "worktrees/713/head",
            "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=False,
    )
    db_session.commit()

    rejected = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "agent-worker-draining"},
    )
    accepted = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "agent-worker-replacement"},
    )

    assert rejected.status_code == 200
    assert rejected.json()["data"] is None
    assert accepted.status_code == 200
    assert accepted.json()["data"]["runId"] == run.id


def test_agent_claim_order_remains_priority_desc_then_queued_at_asc(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _configure(monkeypatch)
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "test-agent-key-queue-governance"},
    )
    now = utc_now()
    runs = [
        create_agent_job(
            db_session,
            task_id=task_id,
            project_id=100,
            input_payload={
                "worktree": f"worktrees/{task_id}/head",
                "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
            },
            completion_context={},
            comparison_mode=False,
        )
        for task_id in (721, 722, 723)
    ]
    jobs = [
        db_session.get(CodeQualitySchedulerJob, run.scheduler_job_id)
        for run in runs
    ]
    jobs[0].priority = 70
    jobs[0].queued_at = now - timedelta(seconds=10)
    jobs[1].priority = 90
    jobs[1].queued_at = now
    jobs[2].priority = 90
    jobs[2].queued_at = now - timedelta(seconds=1)
    db_session.commit()

    claimed_run_ids = [
        client.post(
            "/internal/agent-review/jobs/claim",
            headers=_worker_headers("worker-token-for-agent-review-tests"),
            json={"workerId": f"worker-{index}"},
        ).json()["data"]["runId"]
        for index in range(3)
    ]

    assert claimed_run_ids == [runs[2].id, runs[1].id, runs[0].id]


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
    assert job["claimAttempt"] == 1
    assert job["apiKey"] == "sk-agent-secret-123456"
    assert job["budgets"]["maxTurns"] == 12
    assert "apiKey" not in json.dumps(job["input"])

    missing_attempt = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/heartbeat",
        headers=_worker_headers(token),
        json={"workerId": "worker-1"},
    )
    assert missing_attempt.status_code == 400

    job_heartbeat = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-1",
            "claimAttempt": job["claimAttempt"],
            "runSummary": {"toolCallCount": 3},
        },
    )
    assert job_heartbeat.status_code == 200
    assert job_heartbeat.json()["data"]["cancelRequested"] is False

    # Completion validation is exercised separately with a real ReviewTask/result row;
    # the claim contract itself must never persist or echo the clear key outside this response.
    settings_record = db_session.get(AgentReviewSettings, 1)
    assert "sk-agent-secret-123456" not in settings_record.api_key_ciphertext


def test_two_workers_claim_distinct_queued_jobs(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "sk-agent-secret-123456"},
    )
    runs = [
        create_agent_job(
            db_session,
            task_id=task_id,
            project_id=100,
            input_payload={
                "worktree": f"worktrees/{task_id}/head",
                "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
            },
            completion_context={},
            comparison_mode=True,
        )
        for task_id in (901, 902)
    ]
    db_session.commit()

    first = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-a"},
    ).json()["data"]
    second = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-b"},
    ).json()["data"]

    assert {first["runId"], second["runId"]} == {run.id for run in runs}
    assert first["jobId"] != second["jobId"]
    assert first["claimAttempt"] == second["claimAttempt"] == 1


def test_reclaimed_job_fences_stale_worker_and_isolates_safe_trace(
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
        json={"workerId": "worker-old"},
    )
    run = create_agent_job(
        db_session,
        task_id=903,
        project_id=100,
        input_payload={
            "worktree": "worktrees/903/head",
            "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=True,
    )
    db_session.commit()
    first = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-old"},
    ).json()["data"]
    scheduler_job = db_session.get(CodeQualitySchedulerJob, first["jobId"])
    scheduler_job.lease_expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    second_response = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-new"},
    )
    assert second_response.status_code == 200
    second = second_response.json()["data"]
    assert second["jobId"] == first["jobId"]
    assert second["claimAttempt"] == 2

    stale_owner = client.post(
        f"/internal/agent-review/jobs/{second['jobId']}/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-old",
            "claimAttempt": first["claimAttempt"],
        },
    )
    assert stale_owner.status_code == 409
    assert stale_owner.json()["code"] == "AGENT_JOB_LEASE_LOST"

    stale_attempt = client.post(
        f"/internal/agent-review/jobs/{second['jobId']}/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-new",
            "claimAttempt": first["claimAttempt"],
        },
    )
    assert stale_attempt.status_code == 409
    assert stale_attempt.json()["code"] == "AGENT_JOB_CLAIM_STALE"

    stale_complete = client.post(
        f"/internal/agent-review/jobs/{second['jobId']}/complete",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-old",
            "claimAttempt": first["claimAttempt"],
            "idempotencyKey": second["idempotencyKey"],
            "reviewCard": {
                "summary": "不应保存",
                "overallLevel": "LOW",
                "findings": [],
            },
        },
    )
    assert stale_complete.status_code == 409
    assert stale_complete.json()["code"] == "AGENT_JOB_LEASE_LOST"

    stale_fail = client.post(
        f"/internal/agent-review/jobs/{second['jobId']}/fail",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-new",
            "claimAttempt": first["claimAttempt"],
            "idempotencyKey": second["idempotencyKey"],
            "failureCode": "AGENT_WORKER_ERROR",
        },
    )
    assert stale_fail.status_code == 409
    assert stale_fail.json()["code"] == "AGENT_JOB_CLAIM_STALE"

    stale_cancel = client.post(
        f"/internal/agent-review/jobs/{second['jobId']}/cancelled",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-old",
            "claimAttempt": first["claimAttempt"],
            "idempotencyKey": second["idempotencyKey"],
        },
    )
    assert stale_cancel.status_code == 409
    assert stale_cancel.json()["code"] == "AGENT_JOB_LEASE_LOST"

    accepted = client.post(
        f"/internal/agent-review/jobs/{second['jobId']}/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-new",
            "claimAttempt": second["claimAttempt"],
            "heartbeatSequence": 0,
            "runSummary": {"audit": _trace_audit([])},
        },
    )
    assert accepted.status_code == 200
    events = [
        event
        for event in list_progress(db_session, 903)
        if event["phase"].startswith("AGENT_")
    ]
    reclaimed = next(event for event in events if event["phase"] == "AGENT_RECLAIMED")
    reclaimed_detail = json.loads(reclaimed["detail"])
    assert reclaimed_detail == {
        "runId": run.id,
        "claimAttempt": 2,
        "reasonCode": "LEASE_EXPIRED",
    }
    analyzing_detail = json.loads(
        next(event for event in events if event["phase"] == "AGENT_ANALYZING")[
            "detail"
        ]
    )
    assert analyzing_detail["claimAttempt"] == 2
    heartbeat_detail = json.loads(
        next(event for event in events if event["phase"] == "AGENT_HEARTBEAT")[
            "detail"
        ]
    )
    assert heartbeat_detail["claimAttempt"] == 2
    assert "worker-old" not in json.dumps(events, ensure_ascii=False)
    assert "worker-new" not in json.dumps(events, ensure_ascii=False)


def test_worker_claim_uses_immutable_run_budget_snapshot(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={
            "enabled": True,
            "apiKey": "sk-agent-secret-123456",
            "budgets": {"maxTurns": 14},
        },
    )
    snapshot = default_agent_budgets()
    snapshot["maxTurns"] = 14
    run = create_agent_job(
        db_session,
        task_id=199,
        project_id=100,
        input_payload={
            "worktree": "worktrees/199/head",
            "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
            "budgets": snapshot,
        },
        completion_context={},
        comparison_mode=False,
    )
    db_session.commit()
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"budgets": {"maxTurns": 16}},
    )

    claim = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-budget-snapshot"},
    )

    assert claim.status_code == 200
    assert claim.json()["data"]["runId"] == run.id
    assert claim.json()["data"]["budgets"]["maxTurns"] == 14


def test_agent_trace_persistence_failure_does_not_lose_job_lease(
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
        json={"workerId": "worker-trace-failure"},
    )
    run = create_agent_job(
        db_session,
        task_id=197,
        project_id=100,
        input_payload={
            "worktree": "worktrees/197/head",
            "case": {"changedFiles": ["src/a.py"], "diff": "+safe()"},
        },
        completion_context={},
        comparison_mode=True,
    )
    db_session.commit()
    job = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-trace-failure"},
    ).json()["data"]
    monkeypatch.setattr(
        "app.agent_review.service.append_progress",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("trace unavailable")
        ),
    )

    heartbeat = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-trace-failure",
            "claimAttempt": job["claimAttempt"],
            "heartbeatSequence": 0,
            "runSummary": {"audit": _trace_audit([])},
        },
    )

    assert heartbeat.status_code == 200
    scheduler_job = db_session.get(CodeQualitySchedulerJob, run.scheduler_job_id)
    assert scheduler_job.status == "RUNNING"
    assert scheduler_job.lease_owner == "worker-trace-failure"


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
        "claimAttempt": job["claimAttempt"],
        "idempotencyKey": job["idempotencyKey"],
        "reviewCard": {"summary": "未发现问题", "overallLevel": "LOW", "findings": []},
        "runSummary": {
            "durationMs": 1200,
            "numTurns": 2,
            "toolCallCount": 4,
            "effectiveBudgets": default_agent_budgets(),
            "prompt": "SECRET_PROMPT",
            "query": "SECRET_QUERY",
            "source": "SECRET_SOURCE",
            "assistant": "SECRET_ASSISTANT",
            "reasoning": "SECRET_REASONING",
        },
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
    stale_attempt = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/complete",
        headers=_worker_headers(token),
        json={**payload, "claimAttempt": job["claimAttempt"] + 1},
    )

    assert first.status_code == 200
    assert first.json()["data"]["idempotent"] is False
    assert second.status_code == 200
    assert second.json()["data"]["idempotent"] is True
    assert stale_attempt.status_code == 409
    assert stale_attempt.json()["code"] == "AGENT_JOB_CLAIM_STALE"
    result = list_result_responses(db_session, 199)[0]
    assert result["requestedEngine"] == "AGENT"
    assert result["effectiveEngine"] == "AGENT"
    assert result["agentRunSummary"]["runId"] == run.id
    assert result["agentRunSummary"]["effectiveBudgets"] == default_agent_budgets()
    persisted = db_session.get(AgentReviewRun, run.id)
    assert persisted is not None
    persisted_text = persisted.tool_summary_json or ""
    assert "SECRET_" not in persisted_text


def test_agent_trace_is_incremental_idempotent_and_sanitized(
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
        json={"workerId": "worker-trace"},
    )
    now = datetime.now()
    db_session.add(
        ReviewTask(
            id=198,
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
        task_id=198,
        project_id=100,
        input_payload={
            "worktree": "worktrees/198/head",
            "case": {"id": "task-198", "changedFiles": ["src/a.py"], "diff": "+safe()"},
            "budgets": default_agent_budgets(),
        },
        completion_context={},
        comparison_mode=True,
    )
    db_session.commit()
    job = client.post(
        "/internal/agent-review/jobs/claim",
        headers=_worker_headers(token),
        json={"workerId": "worker-trace"},
    ).json()["data"]
    discovery = {
        "phase": "DISCOVERY",
        "evidenceCallsUsed": 1,
        "evidenceCallsRemaining": 9,
        "sourceBytesRemaining": 199_980,
        "mustSubmit": False,
        "message": "must not be persisted",
    }
    converge = {
        "phase": "CONVERGE",
        "evidenceCallsUsed": 8,
        "evidenceCallsRemaining": 2,
        "sourceBytesRemaining": 199_960,
        "mustSubmit": False,
    }
    submit = {
        "phase": "SUBMIT",
        "evidenceCallsUsed": 10,
        "evidenceCallsRemaining": 0,
        "sourceBytesRemaining": 199_940,
        "mustSubmit": True,
    }
    events = [
        {
            "sequence": 1,
            "tool": "search_code",
            "status": "SUCCESS",
            "durationMs": 2,
            "itemCount": 1,
            "sourceBytes": 20,
            "query": "SECRET_QUERY",
            "queryHash": "0123456789abcdef",
            "path": "D:/private/src/a.py",
            "source": "SECRET_SOURCE",
            "assistant": "SECRET_ASSISTANT",
            "reasoning": "SECRET_REASONING",
            "pathSummary": [
                {
                    "pathHash": "fedcba9876543210",
                    "suffix": ".py",
                    "depth": 3,
                    "path": "src/a.py",
                }
            ],
            "reviewBudget": discovery,
        },
        {
            "sequence": 2,
            "tool": "read_file_range",
            "status": "SUCCESS",
            "durationMs": 3,
            "itemCount": 4,
            "sourceBytes": 20,
            "pathSummary": [],
            "reviewBudget": converge,
        },
        {
            "sequence": 3,
            "tool": "submit_review",
            "status": "SUCCESS",
            "durationMs": 1,
            "itemCount": 0,
            "sourceBytes": 0,
            "pathSummary": [],
            "reviewBudget": submit,
        },
    ]

    first = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-trace",
            "claimAttempt": job["claimAttempt"],
            "heartbeatSequence": 0,
            "runSummary": {
                "prompt": "SECRET_PROMPT",
                "source": "SECRET_SOURCE",
                "reasoning": "SECRET_REASONING",
            },
        },
    )
    repeated = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-trace",
            "claimAttempt": job["claimAttempt"],
            "heartbeatSequence": 0,
            "runSummary": {"audit": _trace_audit(events[:1])},
        },
    )
    converging = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/heartbeat",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-trace",
            "claimAttempt": job["claimAttempt"],
            "heartbeatSequence": 1,
            "runSummary": {"audit": _trace_audit(events[:2])},
        },
    )
    completed = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/complete",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-trace",
            "claimAttempt": job["claimAttempt"],
            "idempotencyKey": job["idempotencyKey"],
            "reviewCard": {
                "summary": "未发现问题",
                "overallLevel": "LOW",
                "findings": [],
            },
            "runSummary": {"audit": _trace_audit(events)},
        },
    )

    assert first.status_code == repeated.status_code == converging.status_code == 200
    assert completed.status_code == 200
    trace = [
        event
        for event in list_progress(db_session, 198)
        if event["phase"].startswith("AGENT_")
        and event["phase"]
        in {
            "AGENT_ANALYZING",
            "AGENT_TOOL_ACTIVITY",
            "AGENT_CONVERGING",
            "AGENT_SUBMITTING",
        }
    ]
    assert [event["phase"] for event in trace] == [
        "AGENT_ANALYZING",
        "AGENT_TOOL_ACTIVITY",
        "AGENT_CONVERGING",
        "AGENT_SUBMITTING",
    ]
    heartbeats = [
        event
        for event in list_progress(db_session, 198)
        if event["phase"] == "AGENT_HEARTBEAT"
    ]
    assert len(heartbeats) == 2
    heartbeat_details = [json.loads(event["detail"]) for event in heartbeats]
    assert [detail["heartbeatSequence"] for detail in heartbeat_details] == [0, 1]
    assert heartbeat_details[-1]["effectiveBudgets"] == default_agent_budgets()
    assert heartbeat_details[-1]["evidenceCallsUsed"] == 8
    assert set(heartbeat_details[-1]) == {
        "runId",
        "claimAttempt",
        "heartbeatSequence",
        "activity",
        "status",
        "phase",
        "toolCallCount",
        "evidenceCallsUsed",
        "sourceBytesReturned",
        "diffBytesReturned",
        "reviewBudget",
        "effectiveBudgets",
    }
    trace_text = json.dumps(trace, ensure_ascii=False)
    heartbeat_text = json.dumps(heartbeats, ensure_ascii=False)
    assert "SECRET_" not in trace_text
    assert "SECRET_" not in heartbeat_text
    assert "D:/private" not in trace_text
    assert '"query"' not in trace_text
    assert "0123456789abcdef" not in trace_text
    assert "fedcba9876543210" not in trace_text
    db_session.refresh(run)
    stored_audit = run.tool_summary_json or ""
    assert "SECRET_" not in stored_audit
    assert "D:/private" not in stored_audit
    assert "0123456789abcdef" not in stored_audit
    assert "fedcba9876543210" not in stored_audit
    assert '"message"' not in stored_audit


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
            "claimAttempt": job["claimAttempt"],
            "idempotencyKey": job["idempotencyKey"],
            "failureCode": "AGENT_TIMEOUT",
            "failureMessage": "timeout",
            "runSummary": {
                "durationMs": 600000,
                "audit": _trace_audit(
                    [
                        {
                            "sequence": 1,
                            "tool": "read_diff_range",
                            "status": "SUCCESS",
                            "durationMs": 2,
                            "itemCount": 2,
                            "sourceBytes": 12,
                            "pathSummary": [],
                            "reviewBudget": {
                                "phase": "DISCOVERY",
                                "evidenceCallsUsed": 1,
                                "evidenceCallsRemaining": 9,
                                "sourceBytesRemaining": 199_988,
                                "mustSubmit": False,
                            },
                        }
                    ]
                ),
            },
        },
    )

    assert failed.status_code == 200
    db_session.refresh(run)
    assert run.status == "TIMED_OUT"
    assert run.effective_engine == "STANDARD_FALLBACK"
    assert scheduled == [run.id]
    assert run.input_json is not None
    assert [
        event["phase"]
        for event in list_progress(db_session, 299)
        if event["phase"] in {"AGENT_ANALYZING", "AGENT_TOOL_ACTIVITY"}
    ] == ["AGENT_ANALYZING", "AGENT_TOOL_ACTIVITY"]


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
    job.queued_at = utc_now() - timedelta(seconds=61)
    db_session.commit()

    expired = expire_exhausted_agent_jobs(db_session)
    db_session.commit()

    db_session.refresh(run)
    assert expired == [run.id]
    assert run.status == "FAILED"
    assert run.effective_engine == "STANDARD_FALLBACK"
    assert run.failure_code == "AGENT_LEASE_EXHAUSTED"


def test_expired_agent_run_schedules_standard_fallback_with_task_project(
    db_session: Session, monkeypatch
) -> None:
    now = datetime.now()
    db_session.add(
        ReviewTask(
            id=305,
            project_id=105,
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
    db_session.flush()
    run = create_agent_job(
        db_session,
        task_id=305,
        project_id=105,
        input_payload={"worktree": "worktrees/305/head", "case": {"changedFiles": ["src/a.py"]}},
        completion_context={},
        comparison_mode=False,
    )
    run.status = "FAILED"
    run.effective_engine = "STANDARD_FALLBACK"
    db_session.commit()
    monkeypatch.setattr("app.code_quality.service._executor.submit", lambda *args, **kwargs: None)

    schedule_agent_standard_fallback(db_session, run.id)
    schedule_agent_standard_fallback(db_session, run.id)

    fallback_job = (
        db_session.query(CodeQualitySchedulerJob)
        .filter(
            CodeQualitySchedulerJob.task_id == 305,
            CodeQualitySchedulerJob.label == "Agent Review 降级 - Standard",
        )
        .one()
    )
    assert fallback_job.project_id == 105
    assert fallback_job.status == "QUEUED"
    assert fallback_job.review_key == run.review_key


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
        json={
            "workerId": "worker-cancel",
            "claimAttempt": job["claimAttempt"],
        },
    )
    assert heartbeat.json()["data"]["cancelRequested"] is True
    acknowledged = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/cancelled",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-cancel",
            "claimAttempt": job["claimAttempt"],
            "idempotencyKey": job["idempotencyKey"],
        },
    )
    assert acknowledged.status_code == 200
    db_session.refresh(run)
    assert run.status == "CANCELLED"
    assert run.failure_code == "AGENT_CANCELLED"
    assert run.input_json is None


def test_agent_worktree_preflight_retries_once_after_transient_failure(
    monkeypatch, tmp_path
) -> None:
    workspace = tmp_path / "worktrees" / "501" / "head"
    task = ReviewTask(id=501, after_sha="a" * 40, commit_sha="a" * 40)
    project = Project(
        id=501,
        name="retry-demo",
        git_provider="GITLAB",
        git_project_id="501",
        repository_url="https://gitlab.example.com/demo/retry.git",
        default_template_code="backend-default",
        status="ENABLED",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    outcomes = [
        {
            "summary": {
                "status": "UNAVAILABLE",
                "failurePhase": "WORKTREE",
            },
            "unavailableContexts": [{"reason": "transient checkout failure"}],
        },
        {
            "summary": {"status": "PREPARED", "failurePhase": None},
            "unavailableContexts": [],
        },
    ]
    calls: list[int] = []

    def prepare(**_kwargs):
        calls.append(len(calls) + 1)
        outcome = outcomes[len(calls) - 1]
        if outcome["summary"]["status"] == "PREPARED":
            workspace.mkdir(parents=True)
        return outcome

    monkeypatch.setattr("app.agent_review.service.task_head_worktree_path", lambda _task_id: workspace)
    monkeypatch.setattr("app.agent_review.service.prepare_local_repository_context", prepare)

    assert _ensure_worktree(task, project) == workspace
    assert calls == [1, 2]


def test_agent_worktree_preflight_accepts_nested_prepared_result(
    monkeypatch, tmp_path
) -> None:
    workspace = tmp_path / "worktrees" / "503" / "head"
    task = ReviewTask(id=503, after_sha="b" * 40, commit_sha="b" * 40)
    project = Project(
        id=503,
        name="prepared-demo",
        git_provider="GITLAB",
        git_project_id="503",
        repository_url="https://gitlab.example.com/demo/prepared.git",
        default_template_code="backend-default",
        status="ENABLED",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    calls: list[int] = []

    def prepare(**_kwargs):
        calls.append(len(calls) + 1)
        workspace.mkdir(parents=True)
        return {
            "summary": {
                "status": "PREPARED",
                "failurePhase": None,
                "worktreeStatus": "CHECKED_OUT",
            },
            "unavailableContexts": [],
        }

    monkeypatch.setattr("app.agent_review.service.task_head_worktree_path", lambda _task_id: workspace)
    monkeypatch.setattr("app.agent_review.service.prepare_local_repository_context", prepare)

    assert _ensure_worktree(task, project) == workspace
    assert calls == [1]


def test_agent_worktree_preflight_preserves_nested_failure_detail(
    monkeypatch, tmp_path
) -> None:
    workspace = tmp_path / "worktrees" / "504" / "head"
    task = ReviewTask(id=504, after_sha="c" * 40, commit_sha="c" * 40)
    project = Project(
        id=504,
        name="failed-demo",
        git_provider="GITLAB",
        git_project_id="504",
        repository_url="https://gitlab.example.com/demo/failed.git",
        default_template_code="backend-default",
        status="ENABLED",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    monkeypatch.setattr("app.agent_review.service.task_head_worktree_path", lambda _task_id: workspace)
    monkeypatch.setattr(
        "app.agent_review.service.prepare_local_repository_context",
        lambda **_kwargs: {
            "summary": {
                "status": "UNAVAILABLE",
                "failurePhase": "WORKTREE",
                "worktreeStatus": "UNAVAILABLE",
            },
            "unavailableContexts": [{"reason": "git worktree add failed"}],
        },
    )

    with pytest.raises(AppError) as captured:
        _ensure_worktree(task, project)

    assert captured.value.code == "AGENT_WORKTREE_UNAVAILABLE"
    assert captured.value.message == "git worktree add failed (failurePhase=WORKTREE, attempts=2)"


def test_agent_preflight_fallback_persists_failure_detail(
    db_session: Session,
) -> None:
    metadata = _agent_preflight_fallback_metadata(
        db_session,
        task_id=502,
        exception=AppError(
            "AGENT_WORKTREE_UNAVAILABLE",
            "git worktree add failed (failurePhase=WORKTREE, attempts=2)",
            409,
        ),
    )
    db_session.commit()

    assert metadata["agentRunSummary"]["failureCode"] == "AGENT_WORKTREE_UNAVAILABLE"
    assert metadata["agentRunSummary"]["failureMessage"].endswith("attempts=2)")
    events = list_progress(db_session, 502)
    assert events[-1]["phase"] == "AGENT_PREFLIGHT_FAILED"
    assert "failureMessage" in events[-1]["detail"]


def test_manual_agent_review_excludes_sensitive_file_and_reaches_worker_queue(
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
        json={
            "enabled": True,
            "apiKey": "sk-agent-secret-123456",
            "budgets": {"maxTurns": 14},
        },
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
            "diffText": (
                "diff --git a/service.py b/service.py\n"
                "--- a/service.py\n"
                "+++ b/service.py\n"
                "@@ -1 +1 @@\n"
                "+value = None\n"
                "diff --git a/src/main/resources/application-prod.properties "
                "b/src/main/resources/application-prod.properties\n"
                "--- a/src/main/resources/application-prod.properties\n"
                "+++ b/src/main/resources/application-prod.properties\n"
                "@@ -1 +1 @@\n"
                "+private.password=must-not-leave-platform"
            ),
            "changedFiles": [
                "service.py",
                "src/main/resources/application-prod.properties",
            ],
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
    assert job["budgets"] == {**default_agent_budgets(), "maxTurns": 14}
    assert job["input"]["diffMode"] == "INLINE"
    assert job["input"]["changedFiles"] == ["service.py"]
    assert "application-prod.properties" not in job["input"]["diff"]
    assert "must-not-leave-platform" not in job["input"]["diff"]
    assert job["input"]["reviewCoverage"] == {
        "totalChangedFileCount": 2,
        "includedFileCount": 1,
        "excludedFileCount": 1,
        "excludedPaths": ["src/main/resources/application-prod.properties"],
    }
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress")
    assert any(
        event["phase"] == "AGENT_SENSITIVE_PATHS_EXCLUDED"
        for event in progress.json()["data"]
    )
    completed = client.post(
        f"/internal/agent-review/jobs/{job['jobId']}/complete",
        headers=_worker_headers(token),
        json={
            "workerId": "worker-1",
            "claimAttempt": job["claimAttempt"],
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


def test_manual_agent_review_skips_when_all_files_are_sensitive(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _encryption_key, token = _configure(monkeypatch)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    client.put(
        "/api/code-quality-reviews/agent-settings",
        json={"enabled": True, "apiKey": "sk-agent-secret-123456"},
    )
    client.post(
        "/internal/agent-review/workers/heartbeat",
        headers=_worker_headers(token),
        json={"workerId": "worker-sensitive"},
    )
    now = datetime.now()
    group = ProjectGroup(
        id=31,
        group_name="Agent 敏感路径项目组",
        group_code="agent-sensitive",
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
        id=306,
        group_id=31,
        name="agent-sensitive-demo",
        git_provider="GITLAB",
        git_project_id="306",
        repository_url="https://gitlab.example.com/demo/agent-sensitive",
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
            "projectId": 306,
            "profileCode": "backend-default-ai-review",
            "reviewEngine": "AGENT",
            "mode": "DIFF_TEXT",
            "commitSha": "d" * 40,
            "title": "All sensitive files",
            "diffText": (
                "diff --git a/src/main/resources/application-prod.properties "
                "b/src/main/resources/application-prod.properties\n"
                "--- a/src/main/resources/application-prod.properties\n"
                "+++ b/src/main/resources/application-prod.properties\n"
                "@@ -1 +1 @@\n"
                "+private.password=must-not-leave-platform"
            ),
            "changedFiles": ["src/main/resources/application-prod.properties"],
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "SKIPPED"
    assert data["reviews"][0]["status"] == "SKIPPED"
    agent_jobs = (
        db_session.query(CodeQualitySchedulerJob)
        .filter(
            CodeQualitySchedulerJob.task_id == data["taskId"],
            CodeQualitySchedulerJob.job_type == "AGENT_REVIEW",
        )
        .all()
    )
    assert agent_jobs == []
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress")
    assert any(
        event["phase"] == "AGENT_ALL_PATHS_EXCLUDED"
        for event in progress.json()["data"]
    )


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
