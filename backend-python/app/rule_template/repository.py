from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.json_utils import page_response, read_json, read_json_array
from app.rule_template.models import RuleTemplate


def template_to_dict(template: RuleTemplate) -> dict:
    config = read_json(template.config_json, {})
    if not isinstance(config, dict):
        config = {}
    focus_change_types = config.get("focusChangeTypes")
    recommended_checks = config.get("recommendedChecks")
    return {
        "id": template.id,
        "templateCode": template.template_code,
        "templateName": template.template_name,
        "targetType": template.target_type,
        "version": template.version,
        "enabledRuleCodes": read_json_array(template.enabled_rule_codes),
        "focusChangeTypes": focus_change_types if isinstance(focus_change_types, list) else [],
        "recommendedChecks": recommended_checks if isinstance(recommended_checks, list) else [],
        "config": config,
        "status": template.status,
        "description": template.description,
    }


def list_enabled_templates(db: Session) -> dict:
    templates = db.scalars(
        select(RuleTemplate)
        .where(RuleTemplate.status == "ENABLED")
        .order_by(RuleTemplate.template_code.asc(), RuleTemplate.version.desc())
    ).all()
    items = [template_to_dict(template) for template in templates]
    return page_response(items, 1, len(items), len(items))


def get_enabled_template(db: Session, template_code: str) -> dict:
    template = db.scalars(
        select(RuleTemplate)
        .where(RuleTemplate.status == "ENABLED", RuleTemplate.template_code == template_code)
        .order_by(RuleTemplate.version.desc())
        .limit(1)
    ).first()
    if template is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Rule template not found: {template_code}", 404)
    return template_to_dict(template)

