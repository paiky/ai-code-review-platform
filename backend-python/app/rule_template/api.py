from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.rule_template.repository import (
    get_enabled_template,
    get_notification_rules,
    list_enabled_templates,
    update_notification_rules,
)


router = APIRouter(prefix="/api/rule-templates", tags=["rule-templates"])


@router.get("")
async def list_rule_templates(db: Session = Depends(get_db)) -> dict:
    return ok(list_enabled_templates(db))


@router.get("/{template_code}")
async def get_rule_template(template_code: str, db: Session = Depends(get_db)) -> dict:
    return ok(get_enabled_template(db, template_code))


@router.get("/{template_code}/notification-rules")
async def get_rule_template_notification_rules(template_code: str, db: Session = Depends(get_db)) -> dict:
    return ok(get_notification_rules(db, template_code))


@router.put("/{template_code}/notification-rules")
async def update_rule_template_notification_rules(
    template_code: str,
    request: dict,
    db: Session = Depends(get_db),
) -> dict:
    return ok(update_notification_rules(db, template_code, request.get("focusRuleCodes")))
