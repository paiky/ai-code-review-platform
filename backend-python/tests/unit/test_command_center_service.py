from datetime import datetime, timezone

from app.command_center.repository import GovernanceBaseCounts, RuntimeBaseCounts
from app.command_center.service import (
    build_governance_snapshot,
    build_runtime_snapshot,
)


def test_runtime_snapshot_has_stable_phase_zero_contract() -> None:
    now = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)

    snapshot = build_runtime_snapshot(
        RuntimeBaseCounts(
            intake_task_count=12,
            active_task_count=3,
            queued_job_count=2,
            running_job_count=1,
        ),
        now=now,
        window_hours=24,
        active_limit=20,
        alert_limit=10,
        project_id=101,
        group_id=7,
    ).model_dump(by_alias=True, mode="json")

    assert snapshot["schemaVersion"] == "command-center-runtime-v1"
    assert snapshot["generatedAt"] == "2026-07-31T02:00:00Z"
    assert snapshot["window"] == {
        "from": "2026-07-30T02:00:00Z",
        "to": "2026-07-31T02:00:00Z",
        "hours": 24,
    }
    assert snapshot["intake"]["taskCount"] == 12
    assert snapshot["intake"]["activeTaskCount"] == 3
    assert snapshot["scheduler"]["activeJobCount"] == 3
    assert snapshot["scheduler"]["queuedJobCount"] == 2
    assert snapshot["scheduler"]["runningJobCount"] == 1
    assert snapshot["activeTasks"] == []
    assert snapshot["activeFlows"] == []
    assert snapshot["coverage"]["phase"] == "PHASE_0"
    assert snapshot["coverage"]["sections"]["activeFlows"] == "DEFERRED"
    assert snapshot["coverage"]["limits"] == {
        "activeLimit": 20,
        "alertLimit": 10,
    }
    assert snapshot["coverage"]["filters"] == {
        "projectId": 101,
        "groupId": 7,
    }


def test_governance_snapshot_marks_basic_and_deferred_sections() -> None:
    now = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)

    snapshot = build_governance_snapshot(
        GovernanceBaseCounts(
            pending_feedback_count=4,
            evaluation_case_count=32,
        ),
        now=now,
        window_hours=48,
        project_id=None,
        group_id=7,
    ).model_dump(by_alias=True, mode="json")

    assert snapshot["schemaVersion"] == "command-center-governance-v1"
    assert snapshot["feedback"] == {
        "status": "BASIC",
        "scope": "CURRENT_STATE",
        "pendingCount": 4,
    }
    assert snapshot["evaluation"] == {
        "status": "BASIC",
        "scope": "ALL_TIME",
        "caseCount": 32,
    }
    assert snapshot["ruleAnalysis"]["status"] == "DEFERRED"
    assert snapshot["findingRisk"]["status"] == "DEFERRED"
    assert snapshot["coverage"]["sections"]["feedback"] == "BASIC"
    assert snapshot["coverage"]["sections"]["evaluation"] == "BASIC"
    assert snapshot["coverage"]["filters"] == {
        "projectId": None,
        "groupId": 7,
    }
