from __future__ import annotations

from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.notification.repository import enabled_webhooks_for_task, has_any_enabled_webhook_for_task


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
    reminder_card_enabled: bool = True,
) -> dict:
    notification_card = filter_risk_card(risk_card, focus_change_types, focus_rule_codes)
    if not reminder_card_enabled or not _has_risk_items(notification_card):
        skipped = {
            "target": "DINGTALK_RISK_CARD",
            "status": "SKIPPED",
            "requestDigest": "No focused reminders matched.",
            "responseBody": None,
            "errorMessage": "No focused reminders matched",
        }
        return _aggregate_results([skipped], skipped["requestDigest"])
    markdown = format_markdown(
        task_id,
        notification_card,
        context,
    )
    digest = markdown[:500]
    return _send_markdown(db, task_id, "变更提醒", markdown, digest, dingtalk_notification_enabled)


def send_review_summary(
    db: Session,
    task_id: int,
    risk_card: dict | None,
    focus_change_types: list[str] | None,
    code_quality_result: dict | None,
    context: dict,
    dingtalk_notification_enabled: bool | None = None,
    focus_rule_codes: list[str] | None = None,
    reminder_card_enabled: bool = True,
) -> dict:
    notification_card = (
        filter_risk_card(risk_card, focus_change_types, focus_rule_codes) if risk_card else None
    )
    if not reminder_card_enabled:
        notification_card = None
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
    return _send_markdown(db, task_id, "变更审查结果", markdown, digest, dingtalk_notification_enabled)


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
    task_id: int,
    title: str,
    markdown: str,
    digest: str,
    dingtalk_notification_enabled: bool | None,
) -> dict:
    settings = get_settings()
    skipped = _resolve_skipped_result(db, digest, dingtalk_notification_enabled, task_id)
    if skipped is not None:
        return _aggregate_results([skipped], digest)

    webhooks = enabled_webhooks_for_task(db, task_id)
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
    task_id: int | None = None,
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

    if has_any_enabled_webhook_for_task(db, task_id):
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
    detail_url = _task_detail_url(task_id)
    result = (
        "### 变更提醒\n\n"
        f"项目：{_project_text(context)}\n\n"
        f"{_event_label(context)} 作者：{_author_text(context)}\n\n"
        "#### 配置变更（规则扫描）\n\n"
        f"{_format_maintenance_reminders(task_id, risk_card)}\n\n"
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
    detail_url = _task_detail_url(task_id)
    result = (
        "### 变更审查结果\n\n"
        f"项目：{_project_text(context)}\n\n"
        f"AI 模型：{_provider_label((code_quality_result or {}).get('provider'))}\n\n"
        f"{_event_label(context)} 作者：{_author_text(context)}\n\n"
    )
    result += (
        "#### 代码质量 Review（AI）\n\n"
        f"{_format_code_quality_summary(task_id, code_quality_result)}\n\n"
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


def _format_maintenance_reminders(task_id: int, risk_card: dict | None) -> str:
    if not risk_card or not risk_card.get("riskItems"):
        return "暂无需要特别维护的变更。"
    grouped_items: dict[str, dict] = {}
    for item in risk_card.get("riskItems", []):
        grouped_items.setdefault(_group_key(str(item.get("category") or "")), item)
    labels = []
    for key, label, color in [
        ("DB", "DB", "#64748b"),
        ("MQ", "MQ", "#d97706"),
        ("CONFIG", "Nacos", "#2563eb"),
        ("CACHE", "Redis", "#dc2626"),
    ]:
        item = grouped_items.get(key)
        if item:
            text = f'<font color="{color}">{label}</font>'
            labels.append(f"* {_risk_item_link(task_id, item, text)}")
    return "\n".join(labels) if labels else "暂无需要特别维护的变更。"


def _format_code_quality_summary(task_id: int, result: dict | None) -> str:
    if not result:
        return "- 未执行代码质量 Review。"
    if result.get("status") != "SUCCESS":
        return "- 代码质量 Review 执行失败，请查看详情。"
    findings = result.get("findings") or []
    if not findings:
        return "- 未发现需要修复的问题。"
    indexed_findings = list(enumerate(findings))
    urgent = [item for item in indexed_findings if _severity_in(item[1], "CRITICAL", "HIGH")]
    possible = [item for item in indexed_findings if _severity_in(item[1], "MAJOR", "MEDIUM")]
    suggestions = [
        item
        for item in indexed_findings
        if not _severity_in(item[1], "CRITICAL", "HIGH", "MAJOR", "MEDIUM")
    ]
    sections = []
    _append_finding_section(sections, task_id, "紧急需要修复", urgent)
    _append_finding_section(sections, task_id, "可能需要修复", possible)
    _append_finding_section(sections, task_id, "建议关注", suggestions)
    return "\n\n".join(sections) if sections else "- 未发现需要修复的问题。"


def _append_finding_section(
    sections: list[str],
    task_id: int,
    title: str,
    findings: list[tuple[int, dict]],
) -> None:
    if not findings:
        return
    items = "\n".join(
        f"- {_finding_link(task_id, index, _concise_finding_title(finding.get('title')))}"
        for index, finding in findings[:5]
    )
    sections.append(f"**{title}：{len(findings)} 个**\n{items}")


def _task_detail_url(task_id: int | None, anchor: str | None = None) -> str:
    if not task_id:
        return ""
    base_url = get_settings().platform_base_url.rstrip("/")
    url = f"{base_url}/tasks/{task_id}"
    return f"{url}#{anchor}" if anchor else url


def _risk_item_link(task_id: int, item: dict, text: str) -> str:
    risk_id = item.get("riskId")
    if not risk_id:
        return text
    return _markdown_link(text, _task_detail_url(task_id, f"risk-item-{quote(str(risk_id), safe='')}"))


def _finding_link(task_id: int, index: int, text: str) -> str:
    return _markdown_link(text, _task_detail_url(task_id, f"fix-preview-{index}"))


def _markdown_link(text: str, url: str) -> str:
    if not url:
        return text
    return f"[{_escape_markdown_link_text(text)}]({url})"


def _escape_markdown_link_text(text: str) -> str:
    return str(text).replace("[", "\\[").replace("]", "\\]")


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
        return code_quality_result is None
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


def _project_text(context: dict) -> str:
    return str(context.get("projectName") or "-")


def _provider_label(provider: str | None) -> str:
    value = str(provider or "").strip().upper()
    labels = {
        "DEEPSEEK": "DeepSeek",
        "OPENAI": "OpenAI",
        "ANTHROPIC": "Anthropic",
        "CUSTOM": "Custom",
        "CODEX_CLI": "Codex CLI",
        "OPENAI_API": "OpenAI API",
        "ANTHROPIC_API": "Anthropic",
    }
    return labels.get(value, value or "-")


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
