from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.json_utils import read_json
from app.code_quality.repository import append_progress
from app.deterministic_checks.repository import (
    create_check_run,
    deterministic_check_run_to_response,
    deterministic_check_security_summary,
    json_dumps,
    latest_check_run,
    list_check_runs,
)
from app.project_integration.models import GitLabMergeRequestEvent, GitLabPushEvent
from app.review_record.models import ReviewTask


CHECK_TYPE_SECRET_SCAN = "SECRET_SCAN"
RULESET_VERSION = "secret-scan-mvp-v1"
MAX_FINDINGS = 50
MAX_EVIDENCE_CHARS = 160

_SECRET_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "PRIVATE_KEY_MARKER",
        re.compile(r"-----BEGIN\s+(?:RSA\s+|DSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----", re.IGNORECASE),
    ),
    (
        "AUTHORIZATION_BEARER",
        re.compile(r"\bAuthorization\b\s*[:=]\s*['\"]?\s*Bearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    ),
    (
        "API_TOKEN_ASSIGNMENT",
        re.compile(r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    ),
    (
        "JDBC_OR_URL_PASSWORD",
        re.compile(r"(?:jdbc:[^\s'\";]+|https?://[^\s'\";]+)[^\s'\";]*(?:password|passwd|pwd)=([^&\s'\";]{4,})", re.IGNORECASE),
    ),
    (
        "SECRET_KEY_ASSIGNMENT",
        re.compile(r"\b(?:secret|secret[_-]?key|client[_-]?secret|password|passwd|pwd)\b\s*[:=]\s*['\"]?[^'\"\s,;]{8,}", re.IGNORECASE),
    ),
)


def get_deterministic_checks_response(db: Session, task_id: int) -> dict[str, Any]:
    _require_task(db, task_id)
    runs = list_check_runs(db, task_id, CHECK_TYPE_SECRET_SCAN)
    latest = runs[0] if runs else None
    return {
        "taskId": task_id,
        "status": latest.status if latest else "NOT_RUN",
        "latestRun": deterministic_check_run_to_response(latest) if latest else None,
        "runs": [deterministic_check_run_to_response(record) for record in runs[:10]],
        "explanation": None if latest else "No deterministic check run has been recorded for this task.",
    }


def run_deterministic_check_response(db: Session, task_id: int, request: dict[str, Any] | None = None) -> dict[str, Any]:
    task = _require_task(db, task_id)
    check_type = str((request or {}).get("checkType") or CHECK_TYPE_SECRET_SCAN).strip().upper()
    if check_type != CHECK_TYPE_SECRET_SCAN:
        raise AppError("VALIDATION_ERROR", f"Unsupported deterministic check type: {check_type}", 400)
    record = _run_secret_scan(db, task, trigger="MANUAL")
    db.commit()
    return deterministic_check_run_to_response(record)


def ensure_deterministic_preflight(
    db: Session,
    task_id: int,
    *,
    changed_files: list[dict[str, Any]] | None = None,
    review_key: str | None = None,
) -> dict[str, Any]:
    """Run one SECRET_SCAN for one Review dispatch before Provider fan-out."""
    task = _require_task(db, task_id)
    append_progress(
        db,
        task_id,
        "DETERMINISTIC_PRECHECK_STARTED",
        "INFO",
        "首次 Review 前确定性检查已开始",
        '{"checkType":"SECRET_SCAN","trigger":"AUTO_PREFLIGHT","scope":"DIFF_ADDED_LINES"}',
        review_key=review_key,
    )
    try:
        record = _run_secret_scan(
            db,
            task,
            changed_files=changed_files,
            trigger="AUTO_PREFLIGHT",
        )
        summary = deterministic_check_security_summary(record)
    except Exception as exception:
        summary = {
            "runId": None,
            "status": "UNAVAILABLE",
            "checkType": CHECK_TYPE_SECRET_SCAN,
            "trigger": "AUTO_PREFLIGHT",
            "freshness": "CURRENT_TASK_INPUT",
            "failureReason": _safe_failure(str(exception) or "Secret scan preflight failed"),
        }
    failed = summary.get("status") in {"FAILED", "UNAVAILABLE"}
    append_progress(
        db,
        task_id,
        "DETERMINISTIC_PRECHECK_FAILED" if failed else "DETERMINISTIC_PRECHECK_COMPLETED",
        "WARN" if failed else "INFO",
        "首次 Review 前确定性检查失败，已降级继续 Review" if failed else "首次 Review 前确定性检查已完成",
        _preflight_progress_detail(summary),
        review_key=review_key,
    )
    db.commit()
    return summary


def latest_security_summary(db: Session | None, task_id: int | None) -> dict[str, Any]:
    if db is None or task_id is None:
        return {
            "status": "NOT_RUN",
            "checkType": CHECK_TYPE_SECRET_SCAN,
            "explanation": "No task id was available when building Context Pack.",
        }
    try:
        return deterministic_check_security_summary(latest_check_run(db, task_id, CHECK_TYPE_SECRET_SCAN))
    except Exception as exception:
        return {
            "status": "UNAVAILABLE",
            "checkType": CHECK_TYPE_SECRET_SCAN,
            "failureReason": _safe_failure(str(exception)),
        }


def _run_secret_scan(
    db: Session,
    task: ReviewTask,
    *,
    changed_files: list[dict[str, Any]] | None = None,
    trigger: str = "MANUAL",
) -> Any:
    started = datetime.now()
    start_counter = perf_counter()
    config = {
        "configSource": "BUILTIN",
        "checkType": CHECK_TYPE_SECRET_SCAN,
        "rulesetVersion": RULESET_VERSION,
        "scope": "DIFF_ADDED_LINES",
        "timeoutMs": 0,
        "maxFindings": MAX_FINDINGS,
        "trigger": trigger,
        "freshness": "CURRENT_TASK_INPUT" if trigger == "AUTO_PREFLIGHT" else "UNKNOWN",
    }
    try:
        files = changed_files if changed_files is not None else _changed_files_from_task(db, task.id)
        scan = _scan_changed_files(files)
        status = "NOT_APPLICABLE" if scan["scannedFileCount"] == 0 or scan["addedLineCount"] == 0 else "COMPLETED"
        summary = {
            "scannedFileCount": scan["scannedFileCount"],
            "addedLineCount": scan["addedLineCount"],
            "findingCount": len(scan["findings"]),
            "ruleTypeCounts": dict(Counter(item["ruleType"] for item in scan["findings"])),
            "truncated": bool(scan["truncated"]),
            "scope": "DIFF_ADDED_LINES",
        }
        failure_reason = None
        findings = scan["findings"]
    except Exception as exception:
        status = "FAILED"
        summary = {
            "scannedFileCount": 0,
            "addedLineCount": 0,
            "findingCount": 0,
            "ruleTypeCounts": {},
            "truncated": False,
            "scope": "DIFF_ADDED_LINES",
        }
        failure_reason = _safe_failure(str(exception) or "Secret scan failed")
        findings = []
    finished = datetime.now()
    duration_ms = max(int((perf_counter() - start_counter) * 1000), 0)
    return create_check_run(
        db,
        {
            "task_id": task.id,
            "project_id": task.project_id,
            "check_type": CHECK_TYPE_SECRET_SCAN,
            "status": status,
            "config_snapshot_json": json_dumps(config),
            "result_summary_json": json_dumps(summary),
            "findings_json": json_dumps(findings),
            "duration_ms": duration_ms,
            "failure_reason": failure_reason,
            "started_at": started,
            "finished_at": finished,
        },
    )


def _scan_changed_files(files: list[dict[str, Any]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    scanned_file_count = 0
    added_line_count = 0
    truncated = False
    for file in files:
        path = _safe_relative_path(file.get("path") or file.get("newPath") or file.get("oldPath"))
        diff_text = str(file.get("diffText") or "")
        if not path or not diff_text.strip():
            continue
        added_lines = list(_iter_added_lines(diff_text))
        if not added_lines:
            continue
        scanned_file_count += 1
        added_line_count += len(added_lines)
        for added in added_lines:
            for rule_type, pattern in _SECRET_RULES:
                if not pattern.search(added["text"]):
                    continue
                if len(findings) >= MAX_FINDINGS:
                    truncated = True
                    break
                findings.append(
                    {
                        "ruleType": rule_type,
                        "filePath": path,
                        "lineNumber": added.get("lineNumber"),
                        "hunkPosition": added.get("hunkPosition"),
                        "evidence": _mask_evidence(added["text"], rule_type),
                    }
                )
                break
            if truncated:
                break
        if truncated:
            break
    return {
        "scannedFileCount": scanned_file_count,
        "addedLineCount": added_line_count,
        "findings": findings,
        "truncated": truncated,
    }


def _iter_added_lines(diff_text: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    new_line: int | None = None
    hunk_position = 0
    for raw_line in diff_text.splitlines():
        if raw_line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", raw_line)
            new_line = int(match.group(1)) if match else None
            hunk_position = 0
            continue
        if raw_line.startswith("+++") or raw_line.startswith("---") or raw_line.startswith("diff --git"):
            continue
        if raw_line.startswith("+"):
            hunk_position += 1
            text = raw_line[1:]
            result.append({"text": text, "lineNumber": new_line, "hunkPosition": hunk_position})
            if new_line is not None:
                new_line += 1
            continue
        if raw_line.startswith("-"):
            hunk_position += 1
            continue
        if new_line is not None and (raw_line.startswith(" ") or raw_line == ""):
            new_line += 1
            hunk_position += 1
    return result


def _changed_files_from_task(db: Session, task_id: int) -> list[dict[str, Any]]:
    mr_event = db.scalars(select(GitLabMergeRequestEvent).where(GitLabMergeRequestEvent.task_id == task_id)).first()
    push_event = db.scalars(select(GitLabPushEvent).where(GitLabPushEvent.task_id == task_id)).first()
    summary = mr_event.changed_files_summary if mr_event is not None else (push_event.changed_files_summary if push_event is not None else None)
    parsed = read_json(summary, {}) if summary else {}
    files = parsed.get("files") if isinstance(parsed, dict) else None
    return [file for file in files if isinstance(file, dict)] if isinstance(files, list) else []


def _require_task(db: Session, task_id: int) -> ReviewTask:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Review task not found: {task_id}", 404)
    return task


def _mask_evidence(line: str, rule_type: str) -> str:
    text = line.strip()
    if rule_type == "PRIVATE_KEY_MARKER":
        return "PRIVATE_KEY_MARKER: ****"
    text = re.sub(r"(Bearer)\s+[A-Za-z0-9._~+/=-]+", r"\1 ****", text, flags=re.IGNORECASE)
    text = re.sub(r"([?&](?:password|passwd|pwd)=)[^&\s'\";]+", r"\1****", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|token|secret|secret[_-]?key|client[_-]?secret|password|passwd|pwd)\b\s*[:=]\s*['\"]?)[^'\"\s,;]+",
        r"\1****",
        text,
        flags=re.IGNORECASE,
    )
    text = _safe_failure(text)
    return text[:MAX_EVIDENCE_CHARS]


def _safe_relative_path(value: Any) -> str | None:
    path = str(value or "").replace("\\", "/").strip()
    if not path:
        return None
    if re.match(r"^[A-Za-z]:/", path) or path.startswith("/"):
        path = path.split("/")[-1]
    while path.startswith("../"):
        path = path[3:]
    return path[:512]


def _safe_failure(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"[A-Za-z]:\\[^\s,;'\"]+", "[local-path]", text)
    text = re.sub(r"/(?:Users|home|var|tmp|app|workspace)/[^\s,;'\"]+", "[local-path]", text)
    text = re.sub(r"(Authorization\s*[:=]\s*Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1****", text, flags=re.IGNORECASE)
    text = re.sub(r"((?:api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*['\"]?)[^'\"\s,;]+", r"\1****", text, flags=re.IGNORECASE)
    return text[:1024]


def _preflight_progress_detail(summary: dict[str, Any]) -> str:
    import json

    return json.dumps(
        {
            "runId": summary.get("runId"),
            "checkType": summary.get("checkType"),
            "status": summary.get("status"),
            "trigger": summary.get("trigger"),
            "freshness": summary.get("freshness"),
            "findingCount": summary.get("findingCount", 0),
            "failureReason": summary.get("failureReason"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
