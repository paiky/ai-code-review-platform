from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4


RISK_WEIGHT = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

CHANGE_TYPE_LABELS = {
    "API": "接口",
    "DB": "数据库",
    "DB_DATA_WRITE": "DB 写入/结构维护",
    "DB_SCHEMA": "DB 表结构",
    "DB_SQL": "SQL",
    "ORM_MAPPING": "ORM/MyBatis 映射",
    "ENTITY_MODEL": "实体模型",
    "DATA_MIGRATION": "数据迁移",
    "CACHE": "缓存",
    "CACHE_WRITE_DELETE": "缓存写入/删除",
    "CACHE_KEY": "缓存 Key",
    "CACHE_TTL": "缓存 TTL",
    "CACHE_INVALIDATION": "缓存失效",
    "CACHE_READ_WRITE": "缓存读写",
    "CACHE_SERIALIZATION": "缓存序列化",
    "MQ": "MQ",
    "MQ_CONFIG": "MQ 配置",
    "MQ_PRODUCER": "MQ 生产者",
    "MQ_CONSUMER": "MQ 消费者",
    "MQ_MESSAGE_SCHEMA": "MQ 消息结构",
    "MQ_TOPIC_CONFIG": "MQ Topic/消费组配置",
    "MQ_RETRY_DLQ": "MQ 重试/死信",
    "CONFIG": "配置",
}

RISK_RULES = {
    "DB_DATA_WRITE_CHANGE_CHECK": ("DB_DATA_WRITE", "HIGH", "DB 写入、表结构或映射变更需要确认", "检测到 DDL、数据写入 SQL、Entity 字段或 MyBatis/ORM 映射变更；纯 select 查询不会触发该提醒。", "可能导致表结构不一致、写入条件错误、字段映射遗漏或历史数据兼容问题。", "HIGH", "出现 DDL / insert / update / delete / Entity / ORM 映射维护信号。", ["确认 insert/update/delete 的 where 条件、影响范围和回滚方案。", "确认实体字段、Mapper 映射与数据库列同步。"], ["BACKEND", "DBA", "QA"]),
    "CACHE_WRITE_DELETE_CHANGE_CHECK": ("CACHE_WRITE_DELETE", "HIGH", "Redis 写入、过期或删除变更需要确认", "检测到缓存 set/put/expire/delete/evict 等写入或失效逻辑变更；纯 get 查询不会触发该提醒。", "可能导致缓存脏数据、误删、TTL 不符合预期或写入后读写不一致。", "HIGH", "出现 Redis 写入、TTL 或删除信号。", ["确认写入、过期和删除策略符合业务一致性要求。"], ["BACKEND", "SRE", "QA"]),
    "MQ_CONFIG_CHANGE_CHECK": ("MQ_CONFIG", "HIGH", "MQ exchange、routeKey 或 queue 配置变更需要确认", "检测到创建 queue、exchange 或 routeKey 的配置变更；只有发送队列消息不会触发该提醒。", "可能导致消息投递到错误 exchange/queue、路由失败或环境配置不一致。", "HIGH", "出现 MQ queue / exchange / routeKey 声明或绑定维护信号。", ["确认 exchange、queue、routeKey 在各环境和中间件控制台已同步。"], ["BACKEND", "SRE", "QA"]),
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
    matching_evidences = [
        evidence
        for evidence in analysis["evidences"]
        if _evidence_matches(rule_code, change_type, evidence["changeType"])
    ]
    evidences = [_risk_evidence(evidence) for evidence in matching_evidences]
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
        "maintenanceArtifacts": _maintenance_artifacts(
            rule_code,
            category,
            resources,
            matching_evidences,
            analysis,
        ),
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


def _maintenance_artifacts(
    rule_code: str,
    category: str,
    resources: list[dict[str, Any]],
    evidences: list[dict[str, Any]],
    analysis: dict,
) -> list[dict[str, Any]]:
    if _is_db_category(category):
        return _db_artifacts(rule_code, category, resources, evidences, analysis)
    if category.startswith("CACHE"):
        return _cache_artifacts(category, evidences)
    if category.startswith("MQ"):
        return _mq_artifacts(category, evidences)
    if category == "CONFIG":
        return _config_artifacts(evidences)
    return []


def _is_db_category(category: str) -> bool:
    return category.startswith("DB") or category in {"ORM_MAPPING", "ENTITY_MODEL", "DATA_MIGRATION"}


def _db_artifacts(
    rule_code: str,
    category: str,
    resources: list[dict[str, Any]],
    evidences: list[dict[str, Any]],
    analysis: dict,
) -> list[dict[str, Any]]:
    sql_lines = _sql_lines(evidences)
    if category in {"DB_DATA_WRITE", "DB_SCHEMA", "DB_SQL", "DATA_MIGRATION"} and rule_code != "DB_SCHEMA_SYNC_SUSPECT_CHECK" and sql_lines:
        return [
            _artifact(
                "SQL",
                "可维护 SQL 片段",
                "sql",
                _join_statement_lines(sql_lines),
                "EXACT",
                _first_file(evidences),
                category,
                "从本次 diff 新增 SQL 行提取，仍建议在目标环境执行前确认执行计划、锁表影响和回滚脚本。",
            )
        ]

    db_evidences = [
        evidence
        for evidence in analysis.get("evidences", [])
        if evidence.get("changeType") in {"DB_DATA_WRITE", "ENTITY_MODEL", "ORM_MAPPING"}
    ]
    return _inferred_db_artifacts(
        category,
        analysis.get("impactedResources", []),
        db_evidences or evidences,
        _exact_schema_tables(analysis.get("evidences", [])),
    )


def _cache_artifacts(category: str, evidences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines = _added_lines(evidences)
    keys = _redis_keys(lines)
    operations = _redis_operations(lines)
    source_lines = _redis_source_lines(lines)
    if not keys and not operations and not source_lines:
        return []
    return [
        _artifact(
            "REDIS_COMMAND",
            "Redis 配置变更信息",
            "text",
            _redis_summary_content(keys, operations, source_lines),
            "EXACT" if keys or operations else "INFERRED",
            _first_file(evidences),
            category,
            "该清单仅用于提示本次新增或修改了 Redis key、写入、删除或过期逻辑；请结合业务场景确认 key 兼容、清理范围和 TTL。",
        )
    ]


def _redis_keys(lines: list[str]) -> list[str]:
    keys: list[str] = []
    for line in lines:
        clean = _clean_code_line(line)
        if not _redis_related(clean):
            continue
        for pattern in [
            r"\b[A-Z0-9_]*(?:REDIS|CACHE)[A-Z0-9_]*\b\s*=\s*([^;]+)",
            r"\b(?:setKey|cacheKey|redisKey|key)\s*=\s*([^;]+)",
            r"(?:redisService|redisTemplate|StringRedisTemplate)\.\w+\s*\(\s*([^,\)]+)",
            r"(?:opsForValue|opsForSet|opsForHash)\s*\(\s*\)\.\w+\s*\(\s*([^,\)]+)",
        ]:
            value = _match(clean, pattern)
            if value:
                keys.append(_clean_redis_value(value))
        quoted = _quoted_cache_key(clean)
        if quoted:
            keys.append(quoted)
    return list(dict.fromkeys(value for value in keys if value and value not in {"this", "null"}))


def _redis_operations(lines: list[str]) -> list[str]:
    operations: list[str] = []
    for line in lines:
        lowered = line.lower()
        if any(value in lowered for value in ["sadd(", ".add(", "opsforset"]):
            operations.append("SET_ADD")
        if any(value in lowered for value in [".set(", ".put(", "setifabsent", "setnx", "opsforvalue"]):
            operations.append("SET_VALUE")
        if any(value in lowered for value in ["del(", "delete(", "evict(", "unlink("]):
            operations.append("DELETE")
        if any(value in lowered for value in ["expire", "ttl", "time-to-live", "timeout"]):
            operations.append("EXPIRE")
    return list(dict.fromkeys(operations))


def _redis_source_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        clean = _clean_code_line(line)
        if not clean or clean.startswith(("import ", "private ", "public class ", "protected ")):
            continue
        if clean.startswith("//") and not _redis_related(clean):
            continue
        if _redis_source_line_relevant(clean):
            result.append(clean)
    return list(dict.fromkeys(result))[:20]


def _redis_summary_content(keys: list[str], operations: list[str], source_lines: list[str]) -> str:
    lines = ["Redis 配置变更信息："]
    if keys:
        lines.append(f"- Key: {', '.join(keys)}")
    if operations:
        lines.append(f"- 操作: {', '.join(_redis_operation_label(value) for value in operations)}")
    if len(lines) == 1:
        lines.append("- 检测到 Redis key / 写入 / 删除 / 过期相关变更。")
    if source_lines:
        lines.extend(["", "关键新增行：", *[f"- {line}" for line in source_lines]])
    return "\n".join(lines)


def _redis_operation_label(value: str) -> str:
    return {
        "SET_ADD": "Set 添加",
        "SET_VALUE": "写入/更新",
        "DELETE": "删除/失效",
        "EXPIRE": "过期/TTL",
    }.get(value, value)


def _redis_related(line: str) -> bool:
    return _contains_any(line, ["redis", "cache", "opsFor", "expire", "delete(", "evict(", "sadd(", "setKey", "LOCK_KEY"])


def _redis_source_line_relevant(line: str) -> bool:
    lowered = line.lower()
    if re.search(r"\b[A-Z0-9_]*(?:REDIS|CACHE)[A-Z0-9_]*\b\s*=", line):
        return True
    return any(
        value in lowered
        for value in [
            "redisservice.",
            "redistemplate.",
            "opsfor",
            ".sadd(",
            ".set(",
            ".put(",
            ".del(",
            ".delete(",
            ".expire(",
            ".evict(",
            "setkey =",
            "cachekey =",
            "rediskey =",
        ]
    )


def _clean_redis_value(value: str) -> str:
    compact = str(value or "").strip().rstrip(";")
    if (compact.startswith('"') and compact.endswith('"')) or (compact.startswith("'") and compact.endswith("'")):
        compact = compact[1:-1]
    return compact.strip()


def _mq_values(lines: list[str], kind: str) -> list[str]:
    patterns = {
        "exchange": [
            r"new\s+(?:TopicExchange|DirectExchange|FanoutExchange|HeadersExchange|CustomExchange)\s*\(\s*([^,\)]+)",
            r"\b[A-Z0-9_]*EXCHANGE\b[^=]*=\s*([^;]+)",
        ],
        "queue": [
            r"new\s+Queue\s*\(\s*([^,\)]+)",
            r"\b[A-Z0-9_]*QUEUE\b[^=]*=\s*([^;]+)",
        ],
        "routeKey": [
            r"\.with\s*\(\s*([^)]+)\)",
            r"\b[A-Z0-9_]*(?:ROUTING_KEY|ROUTE_KEY)\b[^=]*=\s*([^;]+)",
            r"(?i)\b(?:routingKey|routeKey)\s*=\s*([^;]+)",
        ],
    }[kind]
    values: list[str] = []
    for line in lines:
        for pattern in patterns:
            value = _match(line, pattern)
            if value:
                values.append(_clean_mq_value(value))
    return list(dict.fromkeys(value for value in values if value))


def _mq_binding_methods(lines: list[str]) -> list[str]:
    bindings: list[str] = []
    for index, line in enumerate(lines):
        if "BindingBuilder.bind" not in line:
            continue
        method = None
        for previous in reversed(lines[max(0, index - 4) : index]):
            method = _match(previous, r"\b(?:public|private|protected)?\s*Binding\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")
            if method:
                break
        bindings.append(method or _clean_code_line(line))
    return list(dict.fromkeys(bindings))


def _mq_source_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    keywords = [
        "new Queue",
        "TopicExchange",
        "DirectExchange",
        "FanoutExchange",
        "HeadersExchange",
        "CustomExchange",
        "BindingBuilder",
        ".to(",
        ".with(",
        "ROUTING_KEY",
        "ROUTE_KEY",
        "QUEUE",
        "EXCHANGE",
    ]
    for line in lines:
        clean = _clean_code_line(line)
        if not clean or clean in {"}", "};"}:
            continue
        if clean.startswith("//") and not any(keyword in clean for keyword in keywords):
            continue
        if any(keyword in clean for keyword in keywords):
            result.append(clean)
    return list(dict.fromkeys(result))[:20]


def _mq_summary_content(
    exchanges: list[str],
    queues: list[str],
    route_keys: list[str],
    bindings: list[str],
    source_lines: list[str],
) -> str:
    lines = ["MQ 配置变更信息："]
    if exchanges:
        lines.append(f"- Exchange: {', '.join(exchanges)}")
    if queues:
        lines.append(f"- Queue: {', '.join(queues)}")
    if route_keys:
        lines.append(f"- RouteKey: {', '.join(route_keys)}")
    if bindings:
        lines.append(f"- Binding: {', '.join(bindings)}")
    if len(lines) == 1:
        lines.append("- 检测到 queue / exchange / routeKey / binding 相关配置变更。")
    if source_lines:
        lines.extend(["", "关键新增行：", *[f"- {line}" for line in source_lines]])
    return "\n".join(lines)


def _clean_mq_value(value: str) -> str:
    compact = str(value or "").strip().rstrip(";")
    if (compact.startswith('"') and compact.endswith('"')) or (compact.startswith("'") and compact.endswith("'")):
        compact = compact[1:-1]
    return compact.strip()


def _clean_code_line(line: str) -> str:
    return re.sub(r"\s+", " ", str(line or "").strip())


def _mq_artifacts(category: str, evidences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines = _added_lines(evidences)
    if not lines:
        return []
    exchange_values = _mq_values(lines, "exchange")
    queue_values = _mq_values(lines, "queue")
    route_key_values = _mq_values(lines, "routeKey")
    bindings = _mq_binding_methods(lines)
    source_lines = _mq_source_lines(lines)
    content = _mq_summary_content(exchange_values, queue_values, route_key_values, bindings, source_lines)
    return [
        _artifact(
            "MQ_CONFIG_CODE",
            "MQ 配置变更信息",
            "text",
            content,
            "EXACT" if exchange_values or queue_values or route_key_values or bindings else "INFERRED",
            _first_file(evidences),
            category,
            "该清单仅用于提示本次新增或修改了 MQ queue、exchange、routeKey / binding；请到各环境中间件控制台或配置中心确认同步。",
        )
    ]


def _config_artifacts(evidences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for file_path, grouped in _evidences_by_file(evidences).items():
        lines = _added_lines_preserve_indent(grouped)
        if not lines:
            continue
        content_lines = _config_content_lines(file_path, lines)
        if not content_lines:
            continue
        artifacts.append(
            _artifact(
                "NACOS_CONFIG",
                _config_artifact_title(file_path),
                _config_language(file_path),
                "\n".join(content_lines),
                "EXACT",
                file_path,
                "CONFIG",
                "从配置文件或 @Value 新增行提取；复制到 Nacos 前请确认环境、命名空间、默认值和灰度发布策略。",
            )
        )
    return artifacts


def _artifact(
    artifact_type: str,
    title: str,
    language: str,
    content: str,
    confidence: str,
    source_file_path: str | None,
    source_change_type: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "artifactType": artifact_type,
        "title": title,
        "language": language,
        "content": content.strip(),
        "confidence": confidence,
        "copyable": True,
        "sourceFilePath": source_file_path,
        "sourceChangeType": source_change_type,
        "notes": notes,
    }


def _sql_lines(evidences: list[dict[str, Any]]) -> list[str]:
    return [
        line.rstrip(";") + ";"
        for line in _added_lines(evidences)
        if _looks_like_sql_statement(line)
        and not re.search(r"^\s*</?\w+", line)
    ]


def _looks_like_sql_statement(line: str) -> bool:
    compact = line.strip().rstrip(";")
    return bool(
        re.search(
            r"^(create\s+table|alter\s+table|drop\s+table|insert\s+into|update\s+\w+|delete\s+from)\b",
            compact,
            re.I,
        )
    )


def _exact_schema_tables(evidences: list[dict[str, Any]]) -> set[str]:
    tables: set[str] = set()
    for evidence in evidences:
        if evidence.get("changeType") not in {"DB_DATA_WRITE", "DB_SCHEMA", "DATA_MIGRATION"}:
            continue
        for line in _added_lines([evidence]):
            table = _match(line, r"\b(?:create|alter)\s+table\s+[`\"]?([a-zA-Z_][a-zA-Z0-9_]*)[`\"]?")
            if table:
                tables.add(table)
    return tables


def _inferred_db_artifacts(
    category: str,
    resources: list[dict[str, Any]],
    evidences: list[dict[str, Any]],
    exact_schema_tables: set[str],
) -> list[dict[str, Any]]:
    contexts = _db_table_contexts(resources, evidences)
    artifacts: list[dict[str, Any]] = []
    for context in contexts:
        if context["table"] in exact_schema_tables:
            continue
        fields = context["fields"]
        if not fields:
            continue
        is_added_table = context["operation"] == "ADDED" and context["table"] != "<table_name>"
        if is_added_table:
            title = "推断建表 SQL 草稿"
            content = _create_table_sql(context["table"], fields)
            notes = "该建表 SQL 由新增 Entity / Mapper 推断生成，请人工确认主键、字段类型、默认值、索引、字符集和回滚脚本。"
        else:
            title = "推断改表 SQL 草稿"
            content = _alter_table_sql(context["table"], fields)
            notes = "该改表 SQL 由实体字段或 ORM/MyBatis 映射推断生成，请人工确认新增表还是已有表改字段，以及字段类型、默认值、索引和回滚脚本。"
        artifacts.append(
            _artifact(
                "SQL",
                title,
                "sql",
                content,
                "INFERRED",
                context["sourceFilePath"],
                category,
                notes,
            )
        )
    return artifacts


def _db_table_contexts(resources: list[dict[str, Any]], evidences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resource_by_path = _resources_by_path(resources)
    contexts: dict[str, dict[str, Any]] = {}
    for evidence in _prioritized_db_evidences(evidences):
        file_path = str(evidence.get("filePath") or "")
        lines = _added_lines_preserve_indent([evidence])
        table = _table_from_entity_lines(lines) or _resource_table_for_path(resource_by_path, file_path) or _table_from_mapping([evidence])
        if not table:
            table = "<table_name>"
        operation = _resource_operation_for_path(resource_by_path, file_path) or "UNKNOWN"
        context = contexts.setdefault(
            table,
            {
                "table": table,
                "operation": operation,
                "sourceFilePath": file_path or None,
                "fields": [],
            },
        )
        if context["operation"] != "ADDED" and operation == "ADDED":
            context["operation"] = "ADDED"
        if not context["sourceFilePath"] and file_path:
            context["sourceFilePath"] = file_path
        _extend_unique_fields(context["fields"], _entity_fields(lines))
        _extend_unique_fields(context["fields"], _mapping_fields(lines))
    return list(contexts.values())


def _prioritized_db_evidences(evidences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entity_evidences = [
        evidence
        for evidence in evidences
        if _entity_fields(_added_lines_preserve_indent([evidence]))
    ]
    if entity_evidences:
        return entity_evidences
    return evidences


def _resources_by_path(resources: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for resource in resources:
        file_path = str(resource.get("filePath") or "")
        if file_path:
            grouped.setdefault(file_path, []).append(resource)
    return grouped


def _resource_table_for_path(resource_by_path: dict[str, list[dict[str, Any]]], file_path: str) -> str | None:
    for resource in resource_by_path.get(file_path, []):
        if resource.get("resourceType") in {"DB_TABLE", "ORM_MAPPING"}:
            name = str(resource.get("name") or "")
            if name and not name.startswith("src/"):
                return name
    return None


def _resource_operation_for_path(resource_by_path: dict[str, list[dict[str, Any]]], file_path: str) -> str | None:
    for resource in resource_by_path.get(file_path, []):
        operation = resource.get("operation")
        if operation:
            return str(operation).upper()
    return None


def _table_from_entity_lines(lines: list[str]) -> str | None:
    for line in lines:
        table = _match(line, r"@TableName\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']")
        if table:
            return table
    return None


def _entity_fields(lines: list[str]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    pending_column: str | None = None
    pending_primary = False
    for line in lines:
        compact = line.strip()
        table_field = _match(compact, r"@TableField\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']")
        table_id = _match(compact, r"@TableId\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']")
        if table_field:
            pending_column = table_field
            pending_primary = False
            continue
        if table_id:
            pending_column = table_id
            pending_primary = True
            continue
        match = re.search(r"\b(?:private|protected|public)\s+([\w<>?, ]+)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|;)", compact)
        if not match:
            continue
        field_name = match.group(2)
        if field_name == "serialVersionUID" or "static final" in compact:
            pending_column = None
            pending_primary = False
            continue
        fields.append(
            {
                "column": pending_column or _camel_to_snake(field_name),
                "type": _sql_type_for_java(match.group(1).strip().split()[-1]),
                "primary": "true" if pending_primary or field_name == "id" else "false",
            }
        )
        pending_column = None
        pending_primary = False
    return fields


def _mapping_fields(lines: list[str]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    for line in lines:
        column = _match(line, r"column\s*=\s*[\"']([^\"']+)[\"']")
        if not column or column == "*":
            continue
        fields.append(
            {
                "column": column,
                "type": "varchar(255)",
                "primary": "true" if column == "id" else "false",
            }
        )
    return fields


def _extend_unique_fields(target: list[dict[str, str]], fields: list[dict[str, str]]) -> None:
    existing = {field["column"] for field in target}
    for field in fields:
        if field["column"] in existing:
            continue
        target.append(field)
        existing.add(field["column"])


def _create_table_sql(table: str, fields: list[dict[str, str]]) -> str:
    lines = ["-- INFERRED: 请确认主键、字段类型、默认值、索引、字符集和回滚脚本。", f"CREATE TABLE {table} ("]
    primary_keys = [field["column"] for field in fields if field.get("primary") == "true"]
    column_lines = [f"  {field['column']} {field['type']} NULL" for field in fields]
    if primary_keys:
        column_lines.append(f"  PRIMARY KEY ({', '.join(primary_keys[:1])})")
    lines.append(",\n".join(column_lines))
    lines.append(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
    return "\n".join(lines)


def _alter_table_sql(table: str, fields: list[dict[str, str]]) -> str:
    lines = ["-- INFERRED: 请确认新增表还是已有表改字段，以及字段类型、默认值、索引和回滚脚本。"]
    for field in fields:
        lines.append(f"ALTER TABLE {table} ADD COLUMN {field['column']} {field['type']} NULL;")
    return "\n".join(lines)


def _sql_type_for_java(java_type: str) -> str:
    return {
        "String": "varchar(255)",
        "Long": "bigint",
        "long": "bigint",
        "Integer": "int",
        "int": "int",
        "Boolean": "tinyint(1)",
        "boolean": "tinyint(1)",
        "BigDecimal": "decimal(18,2)",
        "Double": "decimal(18,6)",
        "double": "decimal(18,6)",
        "Float": "decimal(18,6)",
        "float": "decimal(18,6)",
        "LocalDateTime": "datetime",
        "LocalDate": "date",
        "Date": "datetime",
    }.get(java_type, "varchar(255)")


def _resource_name(resources: list[dict[str, Any]], resource_type: str) -> str | None:
    for resource in resources:
        if resource.get("resourceType") == resource_type:
            return resource.get("name")
    return None


def _table_from_mapping(evidences: list[dict[str, Any]]) -> str | None:
    for line in _added_lines(evidences):
        value = _match(line, r"\b(?:from|into|update|table|join)\s+[`\"]?([a-zA-Z_][a-zA-Z0-9_]*)[`\"]?")
        if value:
            return value
    return None


def _redis_command(line: str) -> str | None:
    key = _quoted_cache_key(line) or "<key>"
    lowered = line.lower()
    if "delete(" in lowered or "evict" in lowered or "unlink(" in lowered:
        return f"DEL {key}"
    if "expire" in lowered or "ttl" in lowered:
        return f"EXPIRE {key} <seconds>"
    if ".set(" in lowered or ".put(" in lowered or "@cacheput" in lowered:
        return f"SET {key} <value>"
    return None


def _quoted_cache_key(line: str) -> str | None:
    return _match(line, r"[\"']([a-zA-Z0-9_.:-]+:[a-zA-Z0-9_.:-]+)[\"']") or _match(
        line,
        r"(?i)(?:cache[_-]?key|key|prefix|value)\s*=\s*[\"']([^\"']+)[\"']",
    )


def _added_lines(evidences: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for evidence in evidences:
        for line in evidence.get("addedLines") or []:
            line = str(line).strip()
            if line:
                lines.append(line)
    return list(dict.fromkeys(lines))


def _added_lines_preserve_indent(evidences: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for evidence in evidences:
        for line in evidence.get("addedLines") or []:
            line = str(line).rstrip()
            if line.strip():
                lines.append(line)
    return list(dict.fromkeys(lines))


def _evidences_by_file(evidences: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for evidence in evidences:
        file_path = str(evidence.get("filePath") or "__unknown__")
        grouped.setdefault(file_path, []).append(evidence)
    return grouped


def _first_file(evidences: list[dict[str, Any]]) -> str | None:
    for evidence in evidences:
        file_path = evidence.get("filePath")
        if file_path:
            return str(file_path)
    return None


def _first_match(lines: list[str], pattern: str) -> str | None:
    for line in lines:
        value = _match(line, pattern)
        if value:
            return value
    return None


def _match(value: str, pattern: str) -> str | None:
    match = re.search(pattern, value or "", re.I)
    return match.group(1) if match else None


def _contains_any(value: str | None, keywords: list[str]) -> bool:
    normalized = (value or "").lower()
    return any(keyword.lower() in normalized for keyword in keywords)


def _join_statement_lines(lines: list[str]) -> str:
    return "\n".join(dict.fromkeys(line.strip() for line in lines if line.strip()))


def _camel_to_snake(value: str) -> str:
    if "_" in value:
        return value
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _looks_like_config_line(line: str) -> bool:
    return bool(re.search(r"^\s*[a-zA-Z0-9_.-]+\s*[:=]", line) or re.search(r"^\s+[a-zA-Z0-9_.-]+\s*:", line))


def _config_language(file_path: str | None) -> str:
    path = str(file_path or "").lower()
    if path.endswith((".yml", ".yaml")):
        return "yaml"
    if path.endswith(".properties"):
        return "properties"
    return "properties"


def _config_artifact_title(file_path: str | None) -> str:
    if str(file_path or "").lower().endswith((".java", ".kt")):
        return "@Value 配置内容"
    return "可复制 Nacos/配置内容"


def _config_content_lines(file_path: str | None, lines: list[str]) -> list[str]:
    path = str(file_path or "").lower()
    if path.endswith((".yml", ".yaml")):
        return _yaml_config_lines(lines)
    if path.endswith(".properties"):
        return _properties_config_lines(lines)
    return _java_value_config_lines(lines)


def _yaml_config_lines(lines: list[str]) -> list[str]:
    return [
        line.rstrip()
        for line in lines
        if re.search(r"^\s*[a-zA-Z0-9_.-]+\s*:\s*.*$", line)
    ]


def _properties_config_lines(lines: list[str]) -> list[str]:
    return [
        line.strip()
        for line in lines
        if re.search(r"^[a-zA-Z0-9_.-]+\s*[:=]\s*.+$", line.strip())
    ]


def _java_value_config_lines(lines: list[str]) -> list[str]:
    values: list[str] = []
    for line in lines:
        if "@Value(" not in line:
            continue
        key = _match(line, r"\$\{([^}:\s]+)(?::([^}]*))?}")
        default = _match(line, r"\$\{[^}:\s]+:([^}]*)}")
        if key:
            values.append(f"{key}: {default or '<value>'}")
    return list(dict.fromkeys(values))


def _normalize_config_lines(lines: list[str]) -> list[str]:
    normalized: list[str] = []
    for line in lines:
        compact = line.strip()
        value = line.rstrip()
        if compact.startswith("@Value("):
            key = _match(compact, r"\$\{([^}:\s]+)(?::([^}]*))?}")
            default = _match(compact, r"\$\{[^}:\s]+:([^}]*)}")
            if key:
                value = f"{key}: {default or '<value>'}"
        normalized.append(value)
    return normalized


def _card_summary(analysis: dict, risk_level: str, risk_items: list[dict]) -> str:
    if not risk_items:
        return f"未命中需要关注的风险规则。本次分析文件数：{analysis['changedFileCount']}。"
    labels = list(dict.fromkeys(CHANGE_TYPE_LABELS.get(item["category"], item["category"]) for item in risk_items))
    return f"本次重点风险涉及 {', '.join(labels)}，生成 {len(risk_items)} 个风险项，整体风险等级为 {risk_level}。"


def _focus_indicators(analysis: dict, risk_items: list[dict]) -> list[dict]:
    return [
        _focus("DB_SCHEMA_CHANGE", "DB 表/字段变更", {"DB_DATA_WRITE", "DB_SCHEMA", "DATA_MIGRATION", "ENTITY_MODEL", "ORM_MAPPING"}, "HIGH", analysis, risk_items),
        _focus("MQ_CONFIG_CHANGE", "MQ 配置变更", {"MQ_CONFIG", "MQ_TOPIC_CONFIG"}, "MEDIUM", analysis, risk_items),
        _focus("REDIS_CONFIG_CHANGE", "Redis 配置变更", {"CACHE_WRITE_DELETE", "CACHE_KEY", "CACHE_TTL", "CACHE_INVALIDATION", "CACHE_READ_WRITE", "CACHE_SERIALIZATION"}, "MEDIUM", analysis, risk_items),
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
