from __future__ import annotations

import json
from urllib.parse import quote, urlsplit

from sqlalchemy.orm import Session

from app.auto_fix.models import FixRound, FixRun
from app.code_quality.repository import get_settings_record
from app.core.config import get_settings
from app.notification.repository import enabled_webhooks_for_task
from app.notification.service import _markdown_link, _send_to_url, _task_detail_url
from app.project_integration.models import Project
from app.review_record.repository import save_notification_record


_TITLE = "自动修复已完成，等待合并"
_PENDING = {"PENDING", "RETRY_PENDING", "SENDING"}


def _state(run: FixRun) -> dict:
    try:
        payload = json.loads(run.notification_json or "{}")
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state(run: FixRun, targets: dict[str, dict]) -> None:
    statuses = {target["status"] for target in targets.values()}
    if statuses & _PENDING:
        status = "PENDING"
        reason = None
    elif "UNKNOWN" in statuses:
        status = "UNKNOWN"
        reason = "至少一个机器人投递结果未知"
    elif "FAILED" in statuses:
        status = "FAILED"
        reason = "至少一个机器人投递失败"
    elif "SUCCESS" in statuses:
        status = "SUCCESS"
        reason = None if statuses == {"SUCCESS"} else "部分机器人未投递"
    else:
        status = "SKIPPED"
        reason = "无可用机器人"
    run.notification_json = json.dumps(
        {"status": status, "reason": reason, "targets": targets},
        ensure_ascii=False,
    )


def _skip_reason(db: Session) -> str | None:
    if not get_settings().dingtalk_enabled or not get_settings_record(db).dingtalk_notification_enabled:
        return "钉钉通知已关闭"
    return None


def skip_if_pending(run: FixRun) -> None:
    state = _state(run)
    if state.get("status") != "PENDING":
        return
    reason = "修复 MR 已离开等待合并状态"
    targets = state.get("targets") or {}
    if not targets:
        run.notification_json = json.dumps({"status": "SKIPPED", "reason": reason}, ensure_ascii=False)
        return
    for target in targets.values():
        if target["status"] == "SENDING":
            target.update(status="UNKNOWN", reason="上次投递结果无法核实")
        elif target["status"] in _PENDING:
            target.update(status="SKIPPED", reason=reason)
    _save_state(run, targets)


def _link_url(url: str | None) -> str:
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return ""
    except ValueError:
        return ""
    return quote(url, safe=":/?#[]@!$&'*+,;=%~-._")


def _markdown_value(value: str) -> str:
    return "".join(
        f"\\{character}" if character in "\\[]()<>*_~" else character
        for character in " ".join(value.split())
    )


def _card(db: Session, run: FixRun, round_: FixRound) -> str:
    project = db.get(Project, run.project_id)
    project_name = _markdown_value(project.name if project else str(run.project_id))
    branch = _markdown_value(run.developer_branch)
    original_link = _link_url(
        f"{run.project_url.rstrip('/')}/-/merge_requests/{run.source_mr_iid}" if run.project_url else None
    )
    review_link = _link_url(_task_detail_url(round_.review_task_id, review_key=round_.review_key))
    mr_link = _link_url(run.mr_url)
    if not review_link or not mr_link:
        return ""
    original = _markdown_link(f"原 MR !{run.source_mr_iid}", original_link)
    initial_count = sum(
        str(finding.get("severity") or "").strip().upper() == "CRITICAL"
        for finding in json.loads(run.inputs_json).get("findings", [])
    )
    return (
        f"### {_TITLE}\n\n"
        f"- 项目 {project_name} · {original}\n"
        f"- 合并目标 {branch}\n"
        f"- 修复轮数 {round_.number}，紧急风险 {initial_count} → {round_.critical_count}\n\n"
        f"{_markdown_link('最终复审', review_link)} · {_markdown_link('修复 MR', mr_link)}"
    )


def _outcome(response: dict, attempts: int) -> tuple[str, str | None]:
    if response.get("errorMessage") == "HTTP 429" and attempts < 2:
        return "RETRY_PENDING", "机器人限流"
    body = response.get("responseBody")
    if body is None:
        return "UNKNOWN", "投递结果无法核实"
    if response.get("status") != "SUCCESS":
        return "FAILED", "机器人拒绝投递"
    try:
        errcode = json.loads(body).get("errcode")
    except (ValueError, AttributeError):
        return "UNKNOWN", "机器人响应无法核实"
    if (type(errcode) is int and errcode == 0) or errcode == "0":
        return "SUCCESS", None
    if errcode is None:
        return "UNKNOWN", "机器人响应无法核实"
    return "FAILED", "机器人拒绝投递"


def _record(db: Session, run: FixRun, webhook_id: str, status: str, reason: str | None) -> None:
    save_notification_record(
        db, task_id=run.source_task_id, result_id=None,
        target=f"DINGTALK_AUTO_FIX:{webhook_id}", status=status,
        request_digest=f"{_TITLE} · 修复任务 {run.id}", error_message=reason,
    )


def send_if_pending(db: Session, run: FixRun, round_: FixRound) -> None:
    state = _state(run)
    if state.get("status") != "PENDING" or run.status != "AWAITING_APPROVAL" or round_.critical_count != 0:
        return
    targets = state.get("targets")
    webhooks = {}
    reason = _skip_reason(db)
    if reason is None:
        webhooks = {str(item.id): item for item in enabled_webhooks_for_task(db, run.source_task_id)}
    if targets is None:
        targets = {webhook_id: {"status": "PENDING", "attempts": 0} for webhook_id in webhooks}
        if not targets:
            run.notification_json = json.dumps(
                {"status": "SKIPPED", "reason": reason or "项目未配置启用的钉钉机器人"},
                ensure_ascii=False,
            )
            return
    markdown = _card(db, run, round_) if webhooks else ""
    for webhook_id, target in targets.items():
        if target["status"] == "SENDING":
            status, detail = "UNKNOWN", "上次投递结果无法核实"
        elif target["status"] not in _PENDING:
            continue
        elif reason or (current_reason := _skip_reason(db)):
            status, detail = "SKIPPED", reason or current_reason
        elif webhook_id not in webhooks or not markdown:
            status, detail = "SKIPPED", "机器人已停用" if webhook_id not in webhooks else "链接配置不可用"
        else:
            target.update(status="SENDING", attempts=target["attempts"] + 1)
            _save_state(run, targets)
            db.commit()
            # Only persist sanitized outcomes, since the transport result may contain the webhook URL.
            response = _send_to_url(webhooks[webhook_id].webhook_url, _TITLE, markdown, "")
            status, detail = _outcome(response, target["attempts"])
        target.update(status=status, reason=detail)
        _save_state(run, targets)
        if status != "RETRY_PENDING":
            _record(db, run, webhook_id, status, detail)
        db.commit()
