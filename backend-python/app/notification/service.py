import httpx

from app.core.config import get_settings


def dingtalk_skipped_result() -> dict:
    settings = get_settings()
    if not settings.dingtalk_enabled:
        return {
            "target": "DINGTALK_DISABLED",
            "status": "SKIPPED",
            "requestDigest": "DINGTALK_ENABLED=false",
            "responseBody": None,
            "errorMessage": None,
        }
    if not settings.dingtalk_webhook_url.strip():
        return {
            "target": "DINGTALK_WEBHOOK_URL_EMPTY",
            "status": "SKIPPED",
            "requestDigest": "DINGTALK_WEBHOOK_URL is empty",
            "responseBody": None,
            "errorMessage": None,
        }
    return {
        "target": settings.dingtalk_webhook_url,
        "status": "SKIPPED",
        "requestDigest": "DingTalk HTTP send is implemented in stage 3B",
        "responseBody": None,
        "errorMessage": None,
    }


def send_risk_card(task_id: int, risk_card: dict, focus_change_types: list[str], context: dict) -> dict:
    markdown = format_markdown(task_id, filter_risk_card(risk_card, focus_change_types), context)
    digest = markdown[:500]
    return _send_markdown("变更提醒", markdown, digest)


def send_review_summary(
    task_id: int,
    risk_card: dict | None,
    focus_change_types: list[str] | None,
    code_quality_result: dict | None,
    context: dict,
) -> dict:
    notification_card = filter_risk_card(risk_card, focus_change_types) if risk_card else None
    if not _has_risk_items(notification_card) and not _has_code_quality_notification(code_quality_result):
        return {
            "target": "DINGTALK_REVIEW_SUMMARY",
            "status": "SKIPPED",
            "requestDigest": "No focused reminders or code quality findings matched.",
            "responseBody": None,
            "errorMessage": "No focused reminders or code quality findings matched",
        }
    markdown = format_review_summary_markdown(task_id, notification_card, code_quality_result, context)
    digest = markdown[:500]
    return _send_markdown("变更审查结果", markdown, digest)


def _send_markdown(title: str, markdown: str, digest: str) -> dict:
    settings = get_settings()
    if not settings.dingtalk_enabled:
        return {
            "target": "DINGTALK_NOTIFICATION_ENABLED",
            "status": "SKIPPED",
            "requestDigest": digest,
            "responseBody": None,
            "errorMessage": "DingTalk notification is disabled",
        }
    if not settings.dingtalk_webhook_url.strip():
        return {
            "target": "DINGTALK_WEBHOOK_URL",
            "status": "SKIPPED",
            "requestDigest": digest,
            "responseBody": None,
            "errorMessage": "DingTalk webhook is not configured",
        }
    try:
        with httpx.Client(timeout=8) as client:
            response = client.post(
                settings.dingtalk_webhook_url,
                json={"msgtype": "markdown", "markdown": {"title": title, "text": markdown}},
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
        status = "SUCCESS" if 200 <= response.status_code < 300 else "FAILED"
        return {
            "target": settings.dingtalk_webhook_url,
            "status": status,
            "requestDigest": digest,
            "responseBody": response.text,
            "errorMessage": None if status == "SUCCESS" else f"HTTP {response.status_code}",
        }
    except Exception as exception:
        return {
            "target": settings.dingtalk_webhook_url,
            "status": "FAILED",
            "requestDigest": digest,
            "responseBody": None,
            "errorMessage": str(exception),
        }


def filter_risk_card(risk_card: dict, focus_change_types: list[str] | None) -> dict:
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
    reminders = _format_reminders(risk_card.get("riskItems", []))
    detail_url = f"{settings.platform_base_url.rstrip('/')}/?taskId={task_id}" if task_id else ""
    branch = _branch_text(context)
    author = _author_text(context)
    title = context.get("title") or "-"
    link = f"[查看平台详情]({detail_url})" if detail_url else ""
    return (
        "### 变更提醒\n\n"
        f"- **作者：** {author}\n"
        f"- **变更：** {title}\n"
        f"- **分支：** {branch}\n\n"
        f"**提醒**\n{reminders}\n\n"
        f"{link}"
    )


def format_review_summary_markdown(
    task_id: int,
    risk_card: dict | None,
    code_quality_result: dict | None,
    context: dict,
) -> str:
    settings = get_settings()
    detail_url = f"{settings.platform_base_url.rstrip('/')}/?taskId={task_id}" if task_id else ""
    title = str(context.get("title") or "-")
    if title.startswith("GitLab "):
        title = title.removeprefix("GitLab ")
    result = (
        "### 变更审查结果\n\n"
        f"{title}\n"
        f"作者：{_author_text(context)}\n\n"
        "#### 维护提醒（规则扫描）\n\n"
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
        return "- 暂无需要特别维护的变更。"
    groups = {_group_key(str(item.get("category") or "")) for item in risk_card.get("riskItems", [])}
    reminders = []
    if "DB" in groups:
        reminders.append("- 数据库变更：请确认脚本是否需要准备")
    if "MQ" in groups:
        reminders.append("- MQ 变更：请留意 topic、消费组或消息结构是否需要配置")
    if "CACHE" in groups:
        reminders.append("- Redis 变更：请确认缓存 key 是否需要配置")
    if "CONFIG" in groups:
        reminders.append("- 配置变更：请确认是否有新的 Nacos 配置")
    return "\n".join(reminders) if reminders else "- 暂无需要特别维护的变更。"


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


def _branch_text(context: dict) -> str:
    source = context.get("sourceBranch")
    target = context.get("targetBranch")
    if source or target:
        return f"{source or '-'} -> {target or '-'}"
    return "-"
