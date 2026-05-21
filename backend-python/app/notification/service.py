from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.notification.repository import list_enabled_webhooks


def dingtalk_skipped_result(
    db: Session,
    dingtalk_notification_enabled: bool | None = None,
) -> dict:
    return _resolve_skipped_result(db, None, dingtalk_notification_enabled)


def send_risk_card(
    db: Session,
    task_id: int,
    risk_card: dict,
    focus_change_types: list[str],
    context: dict,
    dingtalk_notification_enabled: bool | None = None,
    focus_rule_codes: list[str] | None = None,
) -> dict:
    notification_card = filter_risk_card(risk_card, focus_change_types, focus_rule_codes)
    if _event_label(context) == "Push" and not _has_risk_items(notification_card):
        skipped = {
            "target": "DINGTALK_PUSH_REVIEW_SUMMARY",
            "status": "SKIPPED",
            "requestDigest": "No focused reminders or code quality findings matched.",
            "responseBody": None,
            "errorMessage": "No focused reminders or code quality findings matched",
        }
        return _aggregate_results([skipped], skipped["requestDigest"])
    markdown = format_markdown(
        task_id,
        notification_card,
        context,
    )
    digest = markdown[:500]
    return _send_markdown(db, "变更提醒", markdown, digest, dingtalk_notification_enabled)


def send_review_summary(
    db: Session,
    task_id: int,
    risk_card: dict | None,
    focus_change_types: list[str] | None,
    code_quality_result: dict | None,
    context: dict,
    dingtalk_notification_enabled: bool | None = None,
    focus_rule_codes: list[str] | None = None,
) -> dict:
    notification_card = (
        filter_risk_card(risk_card, focus_change_types, focus_rule_codes) if risk_card else None
    )
    if _should_skip_review_summary(notification_card, code_quality_result, context):
        skipped = {
            "target": "DINGTALK_REVIEW_SUMMARY",
            "status": "SKIPPED",
            "requestDigest": "No focused reminders or code quality findings matched.",
            "responseBody": None,
            "errorMessage": "No focused reminders or code quality findings matched",
        }
        return _aggregate_results([skipped], skipped["requestDigest"])
    markdown = format_review_summary_markdown(task_id, notification_card, code_quality_result, context)
    digest = markdown[:500]
    return _send_markdown(db, "变更审查结果", markdown, digest, dingtalk_notification_enabled)


def send_test_notification(target_url: str, webhook_name: str | None = None) -> dict:
    settings = get_settings()
    if not settings.dingtalk_enabled:
        return {
            "target": target_url,
            "status": "SKIPPED",
            "requestDigest": "DINGTALK_ENABLED=false",
            "responseBody": None,
            "errorMessage": "DingTalk notification is disabled",
        }
    label = webhook_name or "钉钉机器人"
    markdown = (
        f"大家好，我是{label}，很高兴认识大家。"
    )
    return _send_to_url(target_url, f"大家好，我是{label}", markdown, markdown[:500])


def _send_markdown(
    db: Session,
    title: str,
    markdown: str,
    digest: str,
    dingtalk_notification_enabled: bool | None,
) -> dict:
    settings = get_settings()
    skipped = _resolve_skipped_result(db, digest, dingtalk_notification_enabled)
    if skipped is not None:
        return _aggregate_results([skipped], digest)

    webhooks = list_enabled_webhooks(db)
    if not webhooks:
        return _aggregate_results(
            [_send_to_url(settings.dingtalk_webhook_url, title, markdown, digest)],
            digest,
        )
    results = []
    for webhook in webhooks:
        results.append(_send_to_url(webhook.webhook_url, title, markdown, digest))
    return _aggregate_results(results, digest)


def _resolve_skipped_result(
    db: Session,
    digest: str | None,
    dingtalk_notification_enabled: bool | None,
) -> dict | None:
    settings = get_settings()
    if dingtalk_notification_enabled is False:
        return {
            "target": "DINGTALK_NOTIFICATION_ENABLED",
            "status": "SKIPPED",
            "requestDigest": digest or "DingTalk notification is disabled by global setting",
            "responseBody": None,
            "errorMessage": "DingTalk notification is disabled",
        }
    if not settings.dingtalk_enabled:
        return {
            "target": "DINGTALK_DISABLED",
            "status": "SKIPPED",
            "requestDigest": digest or "DINGTALK_ENABLED=false",
            "responseBody": None,
            "errorMessage": None,
        }

    webhooks = list_enabled_webhooks(db)
    if webhooks:
        return None

    if settings.dingtalk_webhook_url.strip():
        return None

    return {
        "target": "DINGTALK_WEBHOOKS_EMPTY",
        "status": "SKIPPED",
        "requestDigest": digest or "No enabled DingTalk webhook is configured",
        "responseBody": None,
        "errorMessage": "DingTalk webhook is not configured",
    }


def _aggregate_results(results: list[dict], digest: str) -> dict:
    if not results:
        results = [
            {
                "target": "DINGTALK_WEBHOOKS_EMPTY",
                "status": "SKIPPED",
                "requestDigest": digest,
                "responseBody": None,
                "errorMessage": "DingTalk webhook is not configured",
            }
        ]
    statuses = {item["status"] for item in results}
    if statuses == {"SUCCESS"}:
        status = "SUCCESS"
        error_message = None
    elif statuses == {"SKIPPED"}:
        status = "SKIPPED"
        error_message = results[0].get("errorMessage")
    elif "SUCCESS" in statuses and "FAILED" in statuses:
        status = "FAILED"
        error_message = "Partial DingTalk webhook delivery failure"
    elif "FAILED" in statuses:
        status = "FAILED"
        error_message = results[0].get("errorMessage")
    else:
        status = "SKIPPED"
        error_message = results[0].get("errorMessage")
    return {
        "target": results[0].get("target"),
        "status": status,
        "requestDigest": digest,
        "responseBody": None,
        "errorMessage": error_message,
        "records": results,
    }


def _send_to_url(target_url: str, title: str, markdown: str, digest: str) -> dict:
    try:
        with httpx.Client(timeout=8) as client:
            response = client.post(
                target_url,
                json={"msgtype": "markdown", "markdown": {"title": title, "text": markdown}},
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
        status = "SUCCESS" if 200 <= response.status_code < 300 else "FAILED"
        return {
            "target": target_url,
            "status": status,
            "requestDigest": digest,
            "responseBody": response.text,
            "errorMessage": None if status == "SUCCESS" else f"HTTP {response.status_code}",
        }
    except Exception as exception:
        return {
            "target": target_url,
            "status": "FAILED",
            "requestDigest": digest,
            "responseBody": None,
            "errorMessage": str(exception),
        }


def filter_risk_card(
    risk_card: dict,
    focus_change_types: list[str] | None,
    focus_rule_codes: list[str] | None = None,
) -> dict:
    rule_focus = {value.strip().upper() for value in focus_rule_codes or [] if value and value.strip()}
    if rule_focus:
        clone = dict(risk_card)
        clone["riskItems"] = [
            item for item in risk_card.get("riskItems", []) if str(item.get("ruleCode", "")).upper() in rule_focus
        ]
        return clone

    if not focus_change_types:
        return risk_card
    focus = {value.strip().upper() for value in focus_change_types if value and value.strip()}
    if not focus:
        return risk_card
    clone = dict(risk_card)
    clone["riskItems"] = [
        item for item in risk_card.get("riskItems", []) if str(item.get("category", "")).upper() in focus
    ]
    return clone


def format_markdown(task_id: int, risk_card: dict, context: dict) -> str:
    settings = get_settings()
    detail_url = f"{settings.platform_base_url.rstrip('/')}/?taskId={task_id}" if task_id else ""
    result = (
        "### 变更提醒\n\n"
        f"{_event_label(context)} 作者：{_author_text(context)}\n\n"
        "#### 配置变更（规则扫描）\n\n"
        f"{_format_maintenance_reminders(risk_card)}\n\n"
    )
    if detail_url:
        result += f"详情：{detail_url}"
    return result


def format_review_summary_markdown(
    task_id: int,
    risk_card: dict | None,
    code_quality_result: dict | None,
    context: dict,
) -> str:
    settings = get_settings()
    detail_url = f"{settings.platform_base_url.rstrip('/')}/?taskId={task_id}" if task_id else ""
    result = (
        "### 变更审查结果\n\n"
        f"{_event_label(context)} 作者：{_author_text(context)}\n\n"
        "#### 配置变更（规则扫描）\n\n"
        f"{_format_maintenance_reminders(risk_card)}\n\n"
        "#### 代码质量 Review（AI）\n\n"
        f"{_format_code_quality_summary(code_quality_result)}\n\n"
    )
    if detail_url:
        result += f"详情：{detail_url}"
    return result


def _format_reminders(risk_items: list[dict]) -> str:
    if not risk_items:
        return "- 本次没有命中需推送的重点提醒。"
    groups: dict[str, int] = {}
    for item in risk_items:
        groups[_group_label(str(item.get("category") or ""))] = groups.get(
            _group_label(str(item.get("category") or "")), 0
        ) + 1
    return "\n".join(f"- {label}：共 {count} 条提醒。" for label, count in groups.items())


def _format_maintenance_reminders(risk_card: dict | None) -> str:
    if not risk_card or not risk_card.get("riskItems"):
        return "暂无需要特别维护的变更。"
    groups = {
        _group_key(str(item.get("category") or ""))
        for item in risk_card.get("riskItems", [])
    }
    labels = []
    for key, label, color in [
        ("DB", "DB", "#64748b"),
        ("MQ", "MQ", "#d97706"),
        ("CONFIG", "Nacos", "#2563eb"),
        ("CACHE", "Redis", "#dc2626"),
    ]:
        if key in groups:
            labels.append(f'* <font color="{color}">{label}</font>')
    return "\n".join(labels) if labels else "暂无需要特别维护的变更。"


def _format_code_quality_summary(result: dict | None) -> str:
    if not result:
        return "- 未执行代码质量 Review。"
    if result.get("status") != "SUCCESS":
        return "- 代码质量 Review 执行失败，请查看详情。"
    findings = result.get("findings") or []
    if not findings:
        return "- 未发现需要修复的问题。"
    urgent = [finding for finding in findings if _severity_in(finding, "CRITICAL", "HIGH")]
    possible = [finding for finding in findings if _severity_in(finding, "MAJOR", "MEDIUM")]
    suggestions = [
        finding
        for finding in findings
        if not _severity_in(finding, "CRITICAL", "HIGH", "MAJOR", "MEDIUM")
    ]
    sections = []
    _append_finding_section(sections, "紧急需要修复", urgent)
    _append_finding_section(sections, "可能需要修复", possible)
    _append_finding_section(sections, "建议关注", suggestions)
    return "\n\n".join(sections) if sections else "- 未发现需要修复的问题。"


def _append_finding_section(sections: list[str], title: str, findings: list[dict]) -> None:
    if not findings:
        return
    items = "\n".join(f"- {_concise_finding_title(finding.get('title'))}" for finding in findings[:5])
    sections.append(f"**{title}：{len(findings)} 个**\n{items}")


def _group_label(category: str) -> str:
    if category.startswith("DB") or category in {"ORM_MAPPING", "ENTITY_MODEL", "DATA_MIGRATION"}:
        return "DB 变更提醒"
    if category.startswith("MQ"):
        return "MQ 变更提醒"
    if category.startswith("CACHE"):
        return "Redis/缓存提醒"
    if category == "CONFIG":
        return "配置提醒"
    return "其他提醒"


def _group_key(category: str) -> str:
    if category.startswith("DB") or category in {"ORM_MAPPING", "ENTITY_MODEL", "DATA_MIGRATION"}:
        return "DB"
    if category.startswith("MQ"):
        return "MQ"
    if category.startswith("CACHE"):
        return "CACHE"
    if category == "CONFIG":
        return "CONFIG"
    return "OTHER"


def _has_risk_items(risk_card: dict | None) -> bool:
    return bool(risk_card and risk_card.get("riskItems"))


def _has_code_quality_notification(result: dict | None) -> bool:
    if not result:
        return False
    if result.get("status") != "SUCCESS":
        return True
    return bool(result.get("findings"))


def _has_code_quality_findings(result: dict | None) -> bool:
    return bool(result and result.get("status") == "SUCCESS" and result.get("findings"))


def _should_skip_review_summary(
    risk_card: dict | None,
    code_quality_result: dict | None,
    context: dict,
) -> bool:
    has_reminders = _has_risk_items(risk_card)
    event_label = _event_label(context)
    if event_label == "MR":
        return False
    if event_label == "Push":
        return not has_reminders and not _has_code_quality_findings(code_quality_result)
    return not has_reminders and not _has_code_quality_notification(code_quality_result)


def _severity_in(finding: dict, *severities: str) -> bool:
    return str(finding.get("severity") or "").upper() in set(severities)


def _concise_finding_title(title: str | None) -> str:
    value = " ".join(str(title or "-").split())
    if len(value) > 48:
        value = value[:45] + "..."
    return value if value.endswith("。") else value + "。"


def _author_text(context: dict) -> str:
    name = context.get("authorName")
    username = context.get("authorUsername")
    if name and username:
        return f"{name}(@{username})"
    if name:
        return name
    if username:
        return f"@{username}"
    return "-"


def _event_label(context: dict) -> str:
    trigger_type = str(context.get("triggerType") or "").upper()
    if trigger_type == "GITLAB_MR_WEBHOOK":
        return "MR"
    if trigger_type == "GITLAB_PUSH_WEBHOOK":
        return "Push"
    if trigger_type == "MANUAL":
        return "Manual"
    title = str(context.get("title") or "").upper()
    if "GITLAB_MR_WEBHOOK" in title:
        return "MR"
    if "GITLAB_PUSH_WEBHOOK" in title:
        return "Push"
    if "MANUAL" in title:
        return "Manual"
    return "Manual"


def _branch_text(context: dict) -> str:
    source = context.get("sourceBranch")
    target = context.get("targetBranch")
    if source or target:
        return f"{source or '-'} -> {target or '-'}"
    return "-"
