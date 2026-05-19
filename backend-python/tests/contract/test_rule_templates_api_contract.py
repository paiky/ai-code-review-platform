from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.rule_template.models import RuleTemplate


def test_rule_templates_api_returns_enabled_templates_and_latest_detail(
    client: TestClient, db_session: Session
) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add_all(
        [
            RuleTemplate(
                id=1,
                template_code="backend-default",
                template_name="后端默认审查模板",
                target_type="BACKEND",
                version=1,
                enabled_rule_codes=json.dumps(["OLD_RULE"]),
                config_json=json.dumps({"focusChangeTypes": ["API"]}),
                status="ENABLED",
                description="old",
                created_at=now,
                updated_at=now,
            ),
            RuleTemplate(
                id=2,
                template_code="backend-default",
                template_name="后端默认审查模板",
                target_type="BACKEND",
                version=2,
                enabled_rule_codes=json.dumps(["DB_SCHEMA_CHANGE_CHECK"]),
                config_json=json.dumps(
                    {
                        "focusChangeTypes": ["DB", "DB_SCHEMA"],
                        "recommendedChecks": ["检查数据库迁移脚本"],
                        "defaultRiskLevel": "LOW",
                    }
                ),
                status="ENABLED",
                description="latest",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    list_response = client.get("/api/rule-templates")
    assert list_response.status_code == 200
    list_data = list_response.json()["data"]
    assert list_data["total"] == 2
    assert [item["version"] for item in list_data["items"]] == [2, 1]

    detail_response = client.get("/api/rule-templates/backend-default")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["version"] == 2
    assert detail["enabledRuleCodes"] == ["DB_SCHEMA_CHANGE_CHECK"]
    assert detail["focusChangeTypes"] == ["DB", "DB_SCHEMA"]
    assert detail["recommendedChecks"] == ["检查数据库迁移脚本"]
    assert detail["config"]["defaultRiskLevel"] == "LOW"


def test_rule_template_detail_not_found_uses_unified_error(
    client: TestClient,
) -> None:
    response = client.get("/api/rule-templates/missing")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["code"] == "RESOURCE_NOT_FOUND"

