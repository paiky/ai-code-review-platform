from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


RISK_WEIGHT = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

CHANGE_TYPE_LABELS = {
    "API": "接口",
    "DB": "数据库",
    "DB_SCHEMA": "DB 表结构",
    "DB_SQL": "SQL",
    "ORM_MAPPING": "ORM/MyBatis 映射",
    "ENTITY_MODEL": "实体模型",
    "DATA_MIGRATION": "数据迁移",
    "CACHE": "缓存",
    "CACHE_KEY": "缓存 Key",
    "CACHE_TTL": "缓存 TTL",
    "CACHE_INVALIDATION": "缓存失效",
    "CACHE_READ_WRITE": "缓存读写",
    "CACHE_SERIALIZATION": "缓存序列化",
    "MQ": "MQ",
    "MQ_PRODUCER": "MQ 生产者",
    "MQ_CONSUMER": "MQ 消费者",
    "MQ_MESSAGE_SCHEMA": "MQ 消息结构",
    "MQ_TOPIC_CONFIG": "MQ Topic/消费组配置",
    "MQ_RETRY_DLQ": "MQ 重试/死信",
    "CONFIG": "配置",
}

RISK_RULES = {
    "DB_SCHEMA_CHANGE_CHECK": ("DB_SCHEMA", "HIGH", "数据库表结构变更需要确认兼容与回滚", "检测到 migration、DDL 或表结构语句发生变化，需要确认历史数据兼容、灰度发布和回滚方案。", "可能导致字段缺失、索引异常、历史数据不兼容或上线后无法快速回滚。", "HIGH", "出现明确 DDL / migration schema 信号。", ["确认 DDL 是否兼容历史数据和线上表规模。", "确认是否需要默认值、回填脚本、索引和回滚脚本。"], ["BACKEND", "DBA", "QA"]),
    "DB_SQL_CHANGE_CHECK": ("DB_SQL", "MEDIUM", "SQL 读写逻辑变更需要确认性能与结果兼容", "检测到 Mapper XML、SQL 文件或代码中的 SQL 读写逻辑发生变化，需要确认查询结果、索引和边界数据。", "可能引入慢 SQL、结果集变化、分页异常或写入条件不一致。", "MEDIUM", "出现 SQL select/insert/update/delete 信号，但未直接发现表结构变更。", ["确认 where、join、order by、limit 和返回字段变化符合预期。", "确认核心 SQL 有索引支撑，并检查大数据量下执行计划。"], ["BACKEND", "DBA", "QA"]),
    "ORM_MAPPING_CHANGE_CHECK": ("ORM_MAPPING", "MEDIUM", "ORM / MyBatis 映射变更需要确认字段兼容", "检测到 resultMap、字段映射、ORM 注解或 Mapper 映射结构发生变化，需要确认实体字段与数据库列保持一致。", "可能导致字段为空、类型转换失败、查询结果映射错误或写入字段遗漏。", "MEDIUM", "出现 resultMap / 字段映射 / ORM 注解信号。", ["确认 resultMap、insert、update 和 select 字段集合与实体字段一致。"], ["BACKEND", "DBA", "QA"]),
    "ENTITY_MODEL_CHANGE_CHECK": ("ENTITY_MODEL", "MEDIUM", "实体模型字段变更需要确认数据库与映射同步", "检测到 Entity / DO / PO 字段或 ORM 注解发生变化，需要确认数据库列、Mapper 映射和序列化兼容。", "可能导致字段未入库、读取为空、类型不兼容或接口返回字段变化。", "MEDIUM", "出现实体字段或 ORM 注解变更信号。", ["确认实体字段变更是否需要对应 migration 或 Mapper 映射变更。"], ["BACKEND", "DBA", "QA"]),
    "DATA_MIGRATION_CHECK": ("DATA_MIGRATION", "HIGH", "数据迁移或历史数据修复需要确认幂等与回滚", "检测到 migration 中包含数据修复、回填或状态转换逻辑，需要确认幂等性、批量执行策略和回滚方案。", "可能导致历史数据不一致、重复回填、锁表或长事务风险。", "HIGH", "出现 migration 数据更新或历史数据修复信号。", ["确认数据修复脚本幂等，可重复执行且有影响范围评估。"], ["BACKEND", "DBA", "SRE", "QA"]),
    "DB_SCHEMA_SYNC_SUSPECT_CHECK": ("ENTITY_MODEL", "HIGH", "疑似实体、映射与数据库结构未同步", "检测到实体字段和 ORM/MyBatis 映射同时变化，但未发现 migration 或 DDL，需要确认是否遗漏表结构变更。", "可能导致代码依赖的字段在数据库中不存在，或 Mapper 与实体模型不一致。", "MEDIUM", "组合信号：entity model changed + ORM mapping changed + migration/DDL not detected。", ["确认本次实体字段变更是否需要新增或修改数据库列。", "如确实不需要 migration，请在 MR 说明中解释原因。"], ["BACKEND", "DBA", "QA"]),
    "CACHE_KEY_CHANGE_CHECK": ("CACHE_KEY", "MEDIUM", "缓存 key 变更需要确认新旧 key 兼容", "检测到缓存 key 命名、前缀或组成维度发生变化，需要确认历史 key、灰度发布和清理策略。", "可能导致命中率骤降、新旧 key 并存、缓存击穿或历史缓存无法清理。", "HIGH", "出现缓存 key 命名或组成变化信号。", ["确认新旧 key 是否需要兼容读取或批量清理。"], ["BACKEND", "QA"]),
    "CACHE_TTL_CHANGE_CHECK": ("CACHE_TTL", "MEDIUM", "缓存 TTL 变更需要确认过期与回源压力", "检测到缓存过期时间、续期或 TTL 策略发生变化，需要确认缓存生命周期和回源压力。", "可能导致缓存雪崩、数据过期不及时、热点数据频繁回源或旧数据停留过久。", "MEDIUM", "出现 expire / ttl / Duration / TimeUnit 等缓存过期策略信号。", ["确认 TTL 变化符合业务实时性和数据一致性要求。"], ["BACKEND", "SRE", "QA"]),
    "CACHE_INVALIDATION_CHANGE_CHECK": ("CACHE_INVALIDATION", "HIGH", "缓存失效策略变更需要确认脏数据风险", "检测到缓存删除、刷新、evict 或 invalidate 逻辑发生变化，需要确认写路径和失效路径一致。", "可能导致更新后仍读取旧缓存、缓存清理遗漏或误删其他业务 key。", "HIGH", "出现 delete / evict / invalidate / @CacheEvict 等缓存失效信号。", ["确认写入或状态变更后会同步失效相关缓存。"], ["BACKEND", "QA"]),
    "CACHE_READ_WRITE_CHANGE_CHECK": ("CACHE_READ_WRITE", "MEDIUM", "缓存读写路径变更需要确认一致性与降级", "检测到缓存读取、写入或回源逻辑发生变化，需要确认 cache-aside、降级和异常处理。", "可能导致缓存穿透、回源异常、读写不一致或缓存不可用时主流程失败。", "MEDIUM", "出现 RedisTemplate / @Cacheable / @CachePut / opsForValue 等缓存读写信号。", ["确认缓存命中、未命中和回源逻辑符合预期。"], ["BACKEND", "QA"]),
    "CACHE_SERIALIZATION_CHANGE_CHECK": ("CACHE_SERIALIZATION", "MEDIUM", "缓存序列化变更需要确认历史值兼容", "检测到缓存序列化器、反序列化逻辑或缓存值结构发生变化，需要确认历史缓存可读取。", "可能导致线上旧缓存反序列化失败、字段缺失或缓存对象版本不兼容。", "MEDIUM", "出现 RedisSerializer / JSON serializer / serialize / deserialize 等缓存序列化信号。", ["确认历史缓存值能被新代码兼容读取。"], ["BACKEND", "QA"]),
    "MQ_PRODUCER_CHANGE_CHECK": ("MQ_PRODUCER", "HIGH", "MQ 生产逻辑变更需要确认发送语义与下游兼容", "检测到 RocketMQ/Kafka/RabbitMQ 生产者发送逻辑发生变化，需要确认 topic、消息体和发送时机。", "可能导致消息少发、多发、发送到错误 topic 或下游消费者无法兼容。", "HIGH", "出现 MQ producer template 或 send / convertAndSend 信号。", ["确认发送 topic、tag、key 和消息体符合消费者契约。"], ["BACKEND", "SRE", "QA"]),
    "MQ_CONSUMER_CHANGE_CHECK": ("MQ_CONSUMER", "HIGH", "MQ 消费逻辑变更需要确认幂等与堆积风险", "检测到 MQ listener、consumer 或消费业务逻辑发生变化，需要确认幂等、异常处理和消费性能。", "可能导致重复消费、消费失败、消息堆积或业务状态错乱。", "HIGH", "出现 MQ listener / consumer 信号。", ["确认消费者具备幂等处理能力。"], ["BACKEND", "SRE", "QA"]),
    "MQ_MESSAGE_SCHEMA_CHANGE_CHECK": ("MQ_MESSAGE_SCHEMA", "HIGH", "MQ 消息体变更需要确认生产者与消费者兼容", "检测到消息 DTO、事件对象或 payload 字段发生变化，需要确认新老生产者和消费者兼容。", "可能导致消息解析失败、字段为空、语义不一致或灰度期间新老版本互不兼容。", "HIGH", "出现 MQ message / event / payload 字段变更信号。", ["确认新增字段有默认值，删除或重命名字段有兼容方案。"], ["BACKEND", "QA", "OWNER"]),
    "MQ_TOPIC_CONFIG_CHANGE_CHECK": ("MQ_TOPIC_CONFIG", "HIGH", "MQ topic/group 配置变更需要确认环境一致性", "检测到 topic、tag、consumerGroup、groupId 或 destination 发生变化，需要确认代码和环境配置一致。", "可能导致消息投递到错误 topic、消费者订阅不到消息或消费组错乱。", "HIGH", "出现 topic / tag / consumerGroup / destination 变更信号。", ["确认各环境 topic、tag 和 consumerGroup 已同步配置。"], ["BACKEND", "SRE", "QA"]),
    "MQ_RETRY_DLQ_CHANGE_CHECK": ("MQ_RETRY_DLQ", "HIGH", "MQ 重试、死信或 ack 变更需要确认失败闭环", "检测到重试、死信、ack/nack、异常捕获或幂等 key 逻辑发生变化，需要确认失败消息处理闭环。", "可能导致重复消费、消息丢失、死信堆积、重试风暴或人工补偿缺失。", "HIGH", "出现 retry / dead letter / ack / idempotency 等失败处理信号。", ["确认失败消息进入可观测、可补偿的路径。"], ["BACKEND", "SRE", "QA"]),
    "CONFIG_RELEASE_CHECK": ("CONFIG", "MEDIUM", "配置变更需要确认灰度、默认值和回滚策略", "检测到 YAML、properties、Nacos 或开关配置发生变化，需要确认配置生效范围和上线策略。", "可能导致环境差异、配置缺失、开关误开或发布后无法快速回滚。", None, None, ["确认新增配置是否有安全默认值。", "确认不同环境配置是否同步。"], ["BACKEND", "SRE", "QA"]),
}


def generate_risk_card(analysis: dict, enabled_rule_codes: list[str], recommended_checks: list[str] | None = None) -> dict:
    risk_items = []
    sequence = 1
    for rule_code in enabled_rule_codes:
        if rule_code == "API_COMPATIBILITY_CHECK":
            continue
        rule = RISK_RULES.get(rule_code)
        if not rule or not _matches(rule_code, rule[0], analysis["changeTypes"]):
            continue
        risk_items.append(_risk_item(sequence, rule_code, rule, analysis))
        sequence += 1

    overall = max((item["riskLevel"] for item in risk_items), key=lambda level: RISK_WEIGHT[level], default="LOW")
    checks = list(dict.fromkeys((recommended_checks or []) + [check for item in risk_items for check in item["recommendedChecks"]]))
    roles = list(dict.fromkeys(role for item in risk_items for role in item["suggestedReviewRoles"]))
    return {
        "cardId": f"risk-card-{uuid4()}",
        "summary": _card_summary(analysis, overall, risk_items),
        "riskLevel": overall,
        "affectedResources": analysis["impactedResources"],
        "focusIndicators": _focus_indicators(analysis, risk_items),
        "riskItems": risk_items,
        "recommendedChecks": checks,
        "suggestedReviewRoles": roles,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "generator": "risk-engine-rule-v1",
    }


def _matches(rule_code: str, change_type: str, change_types: list[str]) -> bool:
    if rule_code == "DB_SCHEMA_SYNC_SUSPECT_CHECK":
        return "ENTITY_MODEL" in change_types and "ORM_MAPPING" in change_types and "DB_SCHEMA" not in change_types
    return change_type in change_types


def _risk_item(sequence: int, rule_code: str, rule: tuple, analysis: dict) -> dict:
    change_type, risk_level, title, description, impact, confidence, reason, checks, roles = rule
    category = "DB_SCHEMA" if rule_code == "DB_SCHEMA_SYNC_SUSPECT_CHECK" else change_type
    evidences = [_risk_evidence(evidence) for evidence in analysis["evidences"] if _evidence_matches(rule_code, change_type, evidence["changeType"])]
    resources = [resource for resource in analysis["impactedResources"] if resource.get("evidence") and _evidence_matches(rule_code, change_type, resource["evidence"]["changeType"])]
    return {
        "riskId": f"{rule_code}-{sequence:03d}",
        "ruleCode": rule_code,
        "category": category,
        "riskLevel": risk_level,
        "title": title,
        "description": description,
        "impact": impact,
        "affectedResources": resources,
        "evidences": evidences,
        "recommendedChecks": checks,
        "suggestedReviewRoles": roles,
        "confidence": confidence,
        "reason": reason,
        "relatedSignals": _related_signals(rule_code, analysis["changeTypes"]),
    }


def _evidence_matches(rule_code: str, rule_change_type: str, actual: str) -> bool:
    if rule_code == "DB_SCHEMA_SYNC_SUSPECT_CHECK":
        return actual in {"ENTITY_MODEL", "ORM_MAPPING"}
    return actual == rule_change_type


def _risk_evidence(evidence: dict) -> dict:
    return {
        "filePath": evidence["filePath"],
        "lineStart": evidence.get("lineStart"),
        "lineEnd": evidence.get("lineEnd"),
        "snippet": evidence.get("snippet"),
        "matcher": evidence.get("matcher"),
    }


def _related_signals(rule_code: str, change_types: list[str]) -> list[str]:
    if rule_code != "DB_SCHEMA_SYNC_SUSPECT_CHECK":
        return []
    signals = []
    if "ENTITY_MODEL" in change_types:
        signals.append("实体模型变更")
    if "ORM_MAPPING" in change_types:
        signals.append("ORM/MyBatis 映射变更")
    if "DB_SCHEMA" not in change_types:
        signals.append("未检测到 migration 或 DDL")
    return signals


def _card_summary(analysis: dict, risk_level: str, risk_items: list[dict]) -> str:
    if not risk_items:
        return f"未命中需要关注的风险规则。本次分析文件数：{analysis['changedFileCount']}。"
    labels = list(dict.fromkeys(CHANGE_TYPE_LABELS.get(item["category"], item["category"]) for item in risk_items))
    return f"本次重点风险涉及 {', '.join(labels)}，生成 {len(risk_items)} 个风险项，整体风险等级为 {risk_level}。"


def _focus_indicators(analysis: dict, risk_items: list[dict]) -> list[dict]:
    return [
        _focus("DB_SCHEMA_CHANGE", "DB 表/字段变更", {"DB_SCHEMA", "DATA_MIGRATION", "ENTITY_MODEL", "ORM_MAPPING"}, "HIGH", analysis, risk_items),
        _focus("MQ_CONFIG_CHANGE", "MQ 配置变更", {"MQ_TOPIC_CONFIG"}, "MEDIUM", analysis, risk_items),
        _focus("REDIS_CONFIG_CHANGE", "Redis 配置变更", {"CACHE_KEY", "CACHE_TTL", "CACHE_INVALIDATION", "CACHE_READ_WRITE", "CACHE_SERIALIZATION"}, "MEDIUM", analysis, risk_items),
        _value_focus(analysis, risk_items),
    ]


def _focus(code: str, name: str, source_types: set[str], default_level: str, analysis: dict, risk_items: list[dict]) -> dict:
    matched_types = [change_type for change_type in analysis["changeTypes"] if change_type in source_types]
    matched = bool(matched_types)
    item_levels = [item["riskLevel"] for item in risk_items if item["category"] in source_types]
    level = max(item_levels, key=lambda value: RISK_WEIGHT[value], default=default_level if matched else None)
    evidences = [_risk_evidence(evidence) for evidence in analysis["evidences"] if evidence["changeType"] in source_types]
    return {
        "code": code,
        "name": name,
        "riskLevel": level,
        "matched": matched,
        "reason": f"命中变更类型：{', '.join(CHANGE_TYPE_LABELS.get(t, t) for t in matched_types)}。" if matched else f"未命中{name}信号。",
        "evidences": evidences,
        "sourceChangeTypes": matched_types,
    }


def _value_focus(analysis: dict, risk_items: list[dict]) -> dict:
    evidences = [_risk_evidence(evidence) for evidence in analysis["evidences"] if evidence.get("matcher") == "VALUE_CONFIG_HEURISTIC_RULE"]
    matched = bool(evidences)
    item_levels = [item["riskLevel"] for item in risk_items if item["category"] == "CONFIG"]
    return {
        "code": "VALUE_CONFIG_CHANGE",
        "name": "@Value 配置变更",
        "riskLevel": max(item_levels, key=lambda value: RISK_WEIGHT[value], default="MEDIUM" if matched else None),
        "matched": matched,
        "reason": "命中 @Value 配置占位符变更。" if matched else "未命中 @Value 配置变更信号。",
        "evidences": evidences,
        "sourceChangeTypes": ["CONFIG"] if matched else [],
    }

