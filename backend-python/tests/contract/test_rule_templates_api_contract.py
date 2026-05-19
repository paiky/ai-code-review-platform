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


def test_rule_template_notification_rules_api_returns_grouped_rules(
    client: TestClient, db_session: Session
) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        RuleTemplate(
            id=3,
            template_code="backend-default",
            template_name="后端默认审查模板",
            target_type="BACKEND",
            version=1,
            enabled_rule_codes=json.dumps(["CONFIG_RELEASE_CHECK"]),
            config_json=json.dumps(
                {
                    "focusChangeTypes": ["DB_SQL"],
                    "focusRuleCodes": ["CONFIG_RELEASE_CHECK"],
                    "recommendedChecks": ["确认配置发布窗口"],
                }
            ),
            status="ENABLED",
            description="notification rules",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()

    response = client.get("/api/rule-templates/backend-default/notification-rules")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["focusRuleCodes"] == ["CONFIG_RELEASE_CHECK"]
    assert [group["groupName"] for group in data["groups"]] == [
        "DB配置变更",
        "MQ配置变更",
        "Redis配置变更",
        "Nacos配置变更",
    ]
    config_rules = data["groups"][3]["rules"]
    assert config_rules[0]["ruleCode"] == "CONFIG_RELEASE_CHECK"
    assert config_rules[0]["enabledInTemplate"] is True
    assert "@Value" in config_rules[0]["example"]
    assert "application.yml" in config_rules[0]["example"]


def test_rule_template_notification_rules_update_preserves_existing_config(
    client: TestClient, db_session: Session
) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        RuleTemplate(
            id=4,
            template_code="backend-default",
            template_name="后端默认审查模板",
            target_type="BACKEND",
            version=1,
            enabled_rule_codes=json.dumps(["DB_SQL_CHANGE_CHECK", "CONFIG_RELEASE_CHECK"]),
            config_json=json.dumps(
                {
                    "focusChangeTypes": ["DB_SQL"],
                    "recommendedChecks": ["确认 SQL 影响范围"],
                    "defaultRiskLevel": "LOW",
                }
            ),
            status="ENABLED",
            description="notification rules update",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()

    response = client.put(
        "/api/rule-templates/backend-default/notification-rules",
        json={"focusRuleCodes": ["CONFIG_RELEASE_CHECK", "DB_SQL_CHANGE_CHECK"]},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["focusRuleCodes"] == ["CONFIG_RELEASE_CHECK", "DB_SQL_CHANGE_CHECK"]
    template = db_session.get(RuleTemplate, 4)
    config = json.loads(template.config_json)
    assert config["focusRuleCodes"] == ["CONFIG_RELEASE_CHECK", "DB_SQL_CHANGE_CHECK"]
    assert config["focusChangeTypes"] == ["DB_SQL"]
    assert config["recommendedChecks"] == ["确认 SQL 影响范围"]
    assert config["defaultRiskLevel"] == "LOW"
