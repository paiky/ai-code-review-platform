from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.rule_template.repository import get_enabled_template, list_enabled_templates


router = APIRouter(prefix="/api/rule-templates", tags=["rule-templates"])


@router.get("")
async def list_rule_templates(db: Session = Depends(get_db)) -> dict:
    return ok(list_enabled_templates(db))


@router.get("/{template_code}")
async def get_rule_template(template_code: str, db: Session = Depends(get_db)) -> dict:
    return ok(get_enabled_template(db, template_code))

