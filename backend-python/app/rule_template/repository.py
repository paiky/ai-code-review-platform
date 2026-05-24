from datetime import datetime
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.json_utils import page_response, read_json, read_json_array
from app.risk_engine.service import RISK_RULES
from app.rule_template.models import RuleTemplate


NOTIFICATION_RULE_GROUPS = [
    {
        "groupCode": "DB",
        "groupName": "DB配置变更",
        "color": "volcano",
        "ruleCodes": [
            "DB_DATA_WRITE_CHANGE_CHECK",
        ],
    },
    {
        "groupCode": "MQ",
        "groupName": "MQ配置变更",
        "color": "blue",
        "ruleCodes": [
            "MQ_CONFIG_CHANGE_CHECK",
        ],
    },
    {
        "groupCode": "REDIS",
        "groupName": "Redis配置变更",
        "color": "green",
        "ruleCodes": [
            "CACHE_WRITE_DELETE_CHANGE_CHECK",
        ],
    },
    {
        "groupCode": "NACOS",
        "groupName": "Nacos配置变更",
        "color": "purple",
        "ruleCodes": ["CONFIG_RELEASE_CHECK"],
    },
]

RULE_EXAMPLES = {
    "DB_DATA_WRITE_CHANGE_CHECK": (
        "OrderMapper.xml\n"
        "+ update orders set status = #{status} where id = #{id}\n\n"
        "OrderDO.java\n"
        "+ @TableField(\"confirm_enabled\")\n"
        "+ private Boolean confirmEnabled;"
    ),
    "CACHE_WRITE_DELETE_CHANGE_CHECK": (
        "OrderCache.java\n"
        "+ redisTemplate.opsForValue().set(\"order:detail:\" + id, value)\n"
        "+ redisTemplate.delete(\"order:list\")"
    ),
    "MQ_CONFIG_CHANGE_CHECK": (
        "RabbitMqBindingConfig.java\n"
        "+ return new Queue(MqClientConstant.REPORT_POSITION_QUEUE, true, false, false);\n"
        "+ return new DirectExchange(MqClientConstant.REPORT_POSITION_EXCHANGE);\n"
        "+ .with(MqClientConstant.REPORT_POSITION_ROUTING_KEY);"
    ),
    "DB_SCHEMA_CHANGE_CHECK": "db/migration/V12__alter_order.sql\n+ alter table orders add column confirm_enabled tinyint",
    "DB_SQL_CHANGE_CHECK": "OrderMapper.xml\n+ update orders set status = #{status} where id = #{id}",
    "ORM_MAPPING_CHANGE_CHECK": "OrderMapper.xml\n+ <result column=\"confirm_enabled\" property=\"confirmEnabled\" />",
    "ENTITY_MODEL_CHANGE_CHECK": "OrderDO.java\n+ private Boolean confirmEnabled;",
    "DATA_MIGRATION_CHECK": "db/migration/V13__backfill_order.sql\n+ update orders set confirm_enabled = 0 where confirm_enabled is null",
    "DB_SCHEMA_SYNC_SUSPECT_CHECK": "实体字段和 Mapper 映射同时新增 confirm_enabled，但没有 migration 文件。",
    "CACHE_KEY_CHANGE_CHECK": "OrderCache.java\n+ redisTemplate.opsForValue().set(\"order:detail:v2:\" + id, value)",
    "CACHE_TTL_CHANGE_CHECK": "OrderCache.java\n+ redisTemplate.expire(key, Duration.ofMinutes(5))",
    "CACHE_INVALIDATION_CHANGE_CHECK": "OrderService.java\n+ redisTemplate.delete(\"order:detail:\" + orderId)",
    "CACHE_READ_WRITE_CHANGE_CHECK": "OrderCache.java\n+ redisTemplate.opsForValue().get(\"order:detail:\" + id)",
    "CACHE_SERIALIZATION_CHANGE_CHECK": "RedisConfig.java\n+ template.setValueSerializer(new GenericJackson2JsonRedisSerializer())",
    "MQ_PRODUCER_CHANGE_CHECK": "OrderProducer.java\n+ rocketMQTemplate.convertAndSend(\"order-paid-topic\", event)",
    "MQ_CONSUMER_CHANGE_CHECK": "OrderPaidConsumer.java\n+ @RocketMQMessageListener(topic = \"order-paid-topic\", consumerGroup = \"order-service\")",
    "MQ_MESSAGE_SCHEMA_CHANGE_CHECK": "OrderPaidEvent.java\n+ private String deviceModel;",
    "MQ_TOPIC_CONFIG_CHANGE_CHECK": "application.yml\n+ rocketmq.consumer.group: order-service-v2",
    "MQ_RETRY_DLQ_CHANGE_CHECK": "OrderConsumer.java\n+ throw new ConsumeRetryLaterException(\"retry later\")",
    "CONFIG_RELEASE_CHECK": (
        "OrderProperties.java\n"
        "+ @Value(\"${order.confirm.enabled:false}\")\n"
        "+ private boolean confirmEnabled;\n\n"
        "application.yml / Nacos\n"
        "+ order:\n"
        "+   confirm:\n"
        "+     enabled: true"
    ),
}

LEGACY_RULE_CODE_MAP = {
    "DB_SCHEMA_CHANGE_CHECK": "DB_DATA_WRITE_CHANGE_CHECK",
    "DB_SQL_CHANGE_CHECK": "DB_DATA_WRITE_CHANGE_CHECK",
    "ORM_MAPPING_CHANGE_CHECK": "DB_DATA_WRITE_CHANGE_CHECK",
    "ENTITY_MODEL_CHANGE_CHECK": "DB_DATA_WRITE_CHANGE_CHECK",
    "DATA_MIGRATION_CHECK": "DB_DATA_WRITE_CHANGE_CHECK",
    "DB_SCHEMA_SYNC_SUSPECT_CHECK": "DB_DATA_WRITE_CHANGE_CHECK",
    "CACHE_KEY_CHANGE_CHECK": "CACHE_WRITE_DELETE_CHANGE_CHECK",
    "CACHE_TTL_CHANGE_CHECK": "CACHE_WRITE_DELETE_CHANGE_CHECK",
    "CACHE_INVALIDATION_CHANGE_CHECK": "CACHE_WRITE_DELETE_CHANGE_CHECK",
    "CACHE_READ_WRITE_CHANGE_CHECK": "CACHE_WRITE_DELETE_CHANGE_CHECK",
    "MQ_PRODUCER_CHANGE_CHECK": "MQ_CONFIG_CHANGE_CHECK",
    "MQ_CONSUMER_CHANGE_CHECK": "MQ_CONFIG_CHANGE_CHECK",
    "MQ_MESSAGE_SCHEMA_CHANGE_CHECK": "MQ_CONFIG_CHANGE_CHECK",
    "MQ_TOPIC_CONFIG_CHANGE_CHECK": "MQ_CONFIG_CHANGE_CHECK",
    "MQ_RETRY_DLQ_CHANGE_CHECK": "MQ_CONFIG_CHANGE_CHECK",
}


def normalize_rule_codes(rule_codes: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for value in rule_codes or []:
        rule_code = str(value or "").strip().upper()
        if not rule_code:
            continue
        rule_code = LEGACY_RULE_CODE_MAP.get(rule_code, rule_code)
        if rule_code not in normalized:
            normalized.append(rule_code)
    return normalized


def template_to_dict(template: RuleTemplate) -> dict:
    config = read_json(template.config_json, {})
    if not isinstance(config, dict):
        config = {}
    focus_change_types = config.get("focusChangeTypes")
    focus_rule_codes = config.get("focusRuleCodes")
    recommended_checks = config.get("recommendedChecks")
    enabled_rule_codes = normalize_rule_codes(read_json_array(template.enabled_rule_codes))
    return {
        "id": template.id,
        "templateCode": template.template_code,
        "templateName": template.template_name,
        "targetType": template.target_type,
        "version": template.version,
        "enabledRuleCodes": enabled_rule_codes,
        "focusChangeTypes": focus_change_types if isinstance(focus_change_types, list) else [],
        "focusRuleCodes": normalize_rule_codes(focus_rule_codes) if isinstance(focus_rule_codes, list) else [],
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
    return template_to_dict(_get_enabled_template_record(db, template_code))


def get_notification_rules(db: Session, template_code: str) -> dict:
    template = _get_enabled_template_record(db, template_code)
    template_data = template_to_dict(template)
    enabled_rule_codes = set(template_data["enabledRuleCodes"])
    return {
        "templateCode": template_data["templateCode"],
        "templateName": template_data["templateName"],
        "version": template_data["version"],
        "focusRuleCodes": template_data["focusRuleCodes"],
        "focusChangeTypes": template_data["focusChangeTypes"],
        "groups": [
            {
                "groupCode": group["groupCode"],
                "groupName": group["groupName"],
                "color": group["color"],
                "rules": [
                    _notification_rule(rule_code, enabled_rule_codes)
                    for rule_code in group["ruleCodes"]
                    if rule_code in RISK_RULES
                ],
            }
            for group in NOTIFICATION_RULE_GROUPS
        ],
    }


def update_notification_rules(db: Session, template_code: str, focus_rule_codes: list[str] | None) -> dict:
    template = _get_enabled_template_record(db, template_code)
    allowed_rule_codes = {
        rule_code
        for group in NOTIFICATION_RULE_GROUPS
        for rule_code in group["ruleCodes"]
    }
    normalized = []
    for value in focus_rule_codes or []:
        rule_code = str(value or "").strip().upper()
        if not rule_code:
            continue
        if rule_code not in allowed_rule_codes:
            raise AppError("VALIDATION_ERROR", f"Unsupported notification rule code: {rule_code}", 400)
        if rule_code not in normalized:
            normalized.append(rule_code)

    config = read_json(template.config_json, {})
    if not isinstance(config, dict):
        config = {}
    config["focusRuleCodes"] = normalized
    template.config_json = json.dumps(config, ensure_ascii=False)
    template.updated_at = datetime.now()
    db.commit()
    return get_notification_rules(db, template_code)


def _get_enabled_template_record(db: Session, template_code: str) -> RuleTemplate:
    template = db.scalars(
        select(RuleTemplate)
        .where(RuleTemplate.status == "ENABLED", RuleTemplate.template_code == template_code)
        .order_by(RuleTemplate.version.desc())
        .limit(1)
    ).first()
    if template is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Rule template not found: {template_code}", 404)
    return template


def _notification_rule(rule_code: str, enabled_rule_codes: set[str]) -> dict:
    change_type, risk_level, title, description, impact, _confidence, _reason, checks, _roles = RISK_RULES[rule_code]
    return {
        "ruleCode": rule_code,
        "changeType": change_type,
        "riskLevel": risk_level,
        "title": title,
        "description": description,
        "impact": impact,
        "recommendedChecks": checks,
        "example": RULE_EXAMPLES.get(rule_code, ""),
        "enabledInTemplate": rule_code in enabled_rule_codes,
    }
