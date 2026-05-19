from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


AGGREGATE_TYPES = {
    "DB_SCHEMA": "DB",
    "DB_SQL": "DB",
    "ORM_MAPPING": "DB",
    "ENTITY_MODEL": "DB",
    "DATA_MIGRATION": "DB",
    "CACHE_KEY": "CACHE",
    "CACHE_TTL": "CACHE",
    "CACHE_INVALIDATION": "CACHE",
    "CACHE_READ_WRITE": "CACHE",
    "CACHE_SERIALIZATION": "CACHE",
    "MQ_PRODUCER": "MQ",
    "MQ_CONSUMER": "MQ",
    "MQ_MESSAGE_SCHEMA": "MQ",
    "MQ_TOPIC_CONFIG": "MQ",
    "MQ_RETRY_DLQ": "MQ",
}

CHANGE_TYPE_ORDER = [
    "API",
    "DB",
    "DB_SCHEMA",
    "DB_SQL",
    "ORM_MAPPING",
    "ENTITY_MODEL",
    "DATA_MIGRATION",
    "CACHE",
    "CACHE_KEY",
    "CACHE_TTL",
    "CACHE_INVALIDATION",
    "CACHE_READ_WRITE",
    "CACHE_SERIALIZATION",
    "MQ",
    "MQ_PRODUCER",
    "MQ_CONSUMER",
    "MQ_MESSAGE_SCHEMA",
    "MQ_TOPIC_CONFIG",
    "MQ_RETRY_DLQ",
    "CONFIG",
]


@dataclass(frozen=True)
class RuleMatch:
    change_type: str
    resource_type: str
    resource_name: str
    reason: str
    matcher: str


def analyze_changes(changed_files: list[dict[str, Any]] | None, diff_text: str | None = None) -> dict:
    files = _normalize_files(changed_files, diff_text)
    all_types: list[str] = []
    impacted_resources: list[dict[str, Any]] = []
    evidences: list[dict[str, Any]] = []
    analyzed_files: list[dict[str, Any]] = []

    for changed_file in files:
        matched_types: list[str] = []
        for match in _analyze_file(changed_file, diff_text):
            _append_type(all_types, match.change_type)
            aggregate = AGGREGATE_TYPES.get(match.change_type)
            if aggregate:
                _append_type(all_types, aggregate)
            _append_type(matched_types, match.change_type)
            if aggregate:
                _append_type(matched_types, aggregate)
            evidence = _evidence(match.change_type, changed_file, f"{match.reason} | {match.resource_name}", match.matcher)
            impacted_resources.append(
                {
                    "resourceType": match.resource_type,
                    "name": match.resource_name,
                    "operation": _change_type(changed_file),
                    "filePath": _effective_path(changed_file),
                    "evidence": evidence,
                }
            )
            evidences.append(evidence)
        analyzed_files.append(
            {
                "path": _effective_path(changed_file),
                "changeType": _change_type(changed_file),
                "matchedChangeTypes": _sort_types(matched_types),
            }
        )

    sorted_types = _sort_types(all_types)
    return {
        "summary": _summary(len(files), sorted_types),
        "changedFileCount": len(files),
        "changeTypes": sorted_types,
        "changedFiles": analyzed_files,
        "impactedResources": impacted_resources,
        "evidences": evidences,
    }


def _normalize_files(changed_files: list[dict[str, Any]] | None, diff_text: str | None) -> list[dict[str, Any]]:
    if changed_files:
        return changed_files
    if diff_text and diff_text.strip():
        return [{"path": "__global_diff__", "changeType": "UNKNOWN", "diffText": diff_text}]
    return []


def _analyze_file(changed_file: dict[str, Any], global_diff_text: str | None) -> list[RuleMatch]:
    content = _content_of(changed_file, global_diff_text)
    matches: list[RuleMatch] = []
    for matcher in (_api_match, _db_match, _cache_match, _mq_match, _config_match, _value_config_match):
        match = matcher(changed_file, content)
        if match:
            matches.append(match)
    return matches


def _api_match(changed_file: dict[str, Any], content: str) -> RuleMatch | None:
    if not (_path_matches(changed_file, ["controller", "endpoint", "/api/", "dto", "request", "response"]) or _contains_any(content, ["@RequestMapping", "@GetMapping", "@PostMapping", "@PutMapping", "@DeleteMapping", "@PatchMapping", "@RestController", "@Controller"])):
        return None
    mapping = re.search(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\([^\"]*\"([^\"]+)\"", content)
    name = f"{mapping.group(1).upper()} {mapping.group(2)}" if mapping else _effective_path(changed_file)
    return RuleMatch("API", "API", name, "Detected API/controller/DTO change", "API_HEURISTIC_RULE")


def _db_match(changed_file: dict[str, Any], content: str) -> RuleMatch | None:
    migration_path = _path_matches(changed_file, ["migration", "db/migration", "schema", "liquibase", "flyway", ".sql"])
    mapper_path = _path_matches(changed_file, ["mapper", "mybatis", "jpa"])
    entity_path = _path_matches(changed_file, ["entity", "/domain/", "\\domain\\", "/model/", "\\model\\", "/po/", "\\po\\", "/do/", "\\do\\"])
    ddl_matched = _contains_any(content, ["create table", "alter table", "drop table", "add column", "drop column", "modify column", "rename column", "create index", "drop index"])
    sql_matched = any(re.search(pattern, content, re.I | re.S) for pattern in [r"\bselect\b.+\bfrom\b", r"\binsert\s+into\b", r"\bupdate\b.+\bset\b", r"\bdelete\s+from\b"])
    orm_matched = _contains_any(content, ["resultMap", "<result ", "<id ", "column=", "property=", "@Table", "@Column", "@JoinColumn", "@OneToMany", "@ManyToOne"])
    entity_matched = re.search(r"@(?:TableField|TableId)\s*\(\s*(?:value\s*=\s*)?[\"']([a-zA-Z_][a-zA-Z0-9_]*)[\"']", content) or (
        entity_path and (_contains_any(content, ["@Entity", "@Table", "@Column", "@TableField", "@TableId", "@TableName"]) or re.search(r"(?m)^\s*[+-]\s*(?:private|protected|public)\s+[\w<>?, ]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|;)", content))
    )
    if ddl_matched:
        return RuleMatch("DB_SCHEMA", "DB_TABLE", _table_name(content, changed_file), "Detected DDL or migration schema statement", "DB_FINE_GRAINED_RULE")
    if migration_path and (sql_matched or _contains_any(content, ["backfill", "migrate", "migration", "数据修复", "回填", "历史数据"])):
        return RuleMatch("DATA_MIGRATION", "DATA_MIGRATION", _table_name(content, changed_file), "Detected migration data change", "DB_FINE_GRAINED_RULE")
    if mapper_path and orm_matched:
        return RuleMatch("ORM_MAPPING", "ORM_MAPPING", _table_name(content, changed_file), "Detected ORM/MyBatis mapping change", "DB_FINE_GRAINED_RULE")
    if entity_matched:
        field = _first_group(content, r"@(?:TableField|TableId)\s*\(\s*(?:value\s*=\s*)?[\"']([a-zA-Z_][a-zA-Z0-9_]*)[\"']") or _first_group(content, r"(?m)^\s*[+-]\s*(?:private|protected|public)\s+[\w<>?, ]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|;)") or _effective_path(changed_file)
        return RuleMatch("ENTITY_MODEL", "ENTITY_FIELD", field, "Detected entity model field or ORM annotation change", "DB_FINE_GRAINED_RULE")
    if sql_matched:
        return RuleMatch("DB_SQL", "DB_TABLE", _table_name(content, changed_file), "Detected SQL read/write logic change", "DB_FINE_GRAINED_RULE")
    return None


def _cache_match(changed_file: dict[str, Any], content: str) -> RuleMatch | None:
    if not (_path_matches(changed_file, ["cache", "redis", "caffeine", "ehcache"]) or _contains_any(content, ["RedisTemplate", "StringRedisTemplate", "@Cacheable", "@CacheEvict", "@CachePut", "cacheManager", "opsForValue", "expire(", "delete(", "RedisSerializer"])):
        return None
    if _contains_any(content, ["RedisSerializer", "Jackson2JsonRedisSerializer", "GenericJackson2JsonRedisSerializer", "StringRedisSerializer", "serialize(", "deserialize(", "ObjectMapper"]):
        change_type, resource_type, reason = "CACHE_SERIALIZATION", "CACHE_VALUE", "Detected cache serialization or cached value schema change"
    elif _contains_any(content, ["@CacheEvict", "delete(", "evict(", "invalidate(", "clear(", "unlink("]):
        change_type, resource_type, reason = "CACHE_INVALIDATION", "CACHE_KEY", "Detected cache invalidation or eviction change"
    elif _contains_any(content, ["expire(", "expireAt(", "ttl", "time-to-live", "timeToLive", "Duration.of", "TimeUnit."]):
        change_type, resource_type, reason = "CACHE_TTL", "CACHE_POLICY", "Detected cache TTL or expiration policy change"
    elif _contains_any(content, ["@Cacheable", "@CachePut", "opsForValue", "opsForHash", "get(", "set(", "put(", "cacheManager"]):
        change_type, resource_type, reason = "CACHE_READ_WRITE", "CACHE_KEY", "Detected cache read/write path change"
    else:
        change_type, resource_type, reason = "CACHE_KEY", "CACHE_KEY", "Detected cache key naming or composition change"
    name = _first_group(content, r"[\"']([a-zA-Z0-9_.:-]+:[a-zA-Z0-9_.:-]+)[\"']") or _first_group(content, r"(?i)(?:cache[_-]?key|key|prefix)\s*(?:=|:)\s*[\"']([a-zA-Z0-9_.:-]+)[\"']") or _effective_path(changed_file)
    return RuleMatch(change_type, resource_type, name, reason, "CACHE_FINE_GRAINED_RULE")


def _mq_match(changed_file: dict[str, Any], content: str) -> RuleMatch | None:
    if not (_path_matches(changed_file, ["mq", "message", "producer", "consumer", "listener", "rocketmq", "kafka", "rabbit"]) or _contains_any(content, ["@RocketMQMessageListener", "RocketMQTemplate", "KafkaTemplate", "@KafkaListener", "RabbitTemplate", "@RabbitListener", "sendMessage", "convertAndSend", "topic", "consumerGroup", "rocketmq", "kafka", "rabbitmq"])):
        return None
    if _contains_any(content, ["retry", "reconsume", "dead letter", "deadLetter", "dlq", "ack", "nack", "manualAck", "maxAttempts", "delayLevel", "idempotent", "idempotency"]):
        change_type, resource_type, reason = "MQ_RETRY_DLQ", "MQ_CONSUMER", "Detected MQ retry, dead-letter, ack or idempotency change"
    elif _contains_any(content, ["RocketMQTemplate", "KafkaTemplate", "RabbitTemplate", "sendMessage", "convertAndSend", "syncSend", "asyncSend", "send("]):
        change_type, resource_type, reason = "MQ_PRODUCER", "MQ_PRODUCER", "Detected MQ producer send logic change"
    elif _contains_any(content, ["@RocketMQMessageListener", "@KafkaListener", "@RabbitListener", "MessageListener", "Consumer", "Listener"]):
        change_type, resource_type, reason = "MQ_CONSUMER", "MQ_CONSUMER", "Detected MQ consumer listener logic change"
    elif _path_matches(changed_file, ["message", "event", "payload", "dto"]) and re.search(r"(?m)^\s*[+-]\s*(?:private|protected|public)\s+[\w<>?, ]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|;)", content):
        change_type, resource_type, reason = "MQ_MESSAGE_SCHEMA", "MQ_MESSAGE", "Detected MQ message payload schema change"
    else:
        change_type, resource_type, reason = "MQ_TOPIC_CONFIG", "MQ_TOPIC", "Detected MQ topic, group or middleware configuration change"
    name = _first_group(content, r"(?i)(?:topic|topics|destination)\s*=\s*[\"']([a-zA-Z0-9_.:-]+)[\"']") or _first_group(content, r"(?i)(?:send|syncSend|asyncSend|convertAndSend)\s*\(\s*[\"']([a-zA-Z0-9_.:-]+)[\"']") or _effective_path(changed_file)
    if change_type == "MQ_MESSAGE_SCHEMA":
        name = _first_group(content, r"(?m)^\s*[+-]\s*(?:private|protected|public)\s+[\w<>?, ]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|;)") or name
    return RuleMatch(change_type, resource_type, name, reason, "MQ_FINE_GRAINED_RULE")


def _config_match(changed_file: dict[str, Any], content: str) -> RuleMatch | None:
    if not (_path_matches(changed_file, ["application.yml", "application.yaml", "application.properties", "bootstrap.yml", "bootstrap.yaml", "nacos", "config", ".properties", ".yaml", ".yml"]) or _contains_any(content, ["spring:", "server:", "datasource:", "redis:", "rocketmq:", "kafka:", "nacos", "feature", "enabled:"])):
        return None
    name = _first_group(content, r"(?m)^\s*[+-]?\s*([a-zA-Z0-9_.-]+)\s*[:=]") or _effective_path(changed_file)
    return RuleMatch("CONFIG", "CONFIG_KEY", name, "Detected configuration change", "CONFIG_HEURISTIC_RULE")


def _value_config_match(changed_file: dict[str, Any], content: str) -> RuleMatch | None:
    if "@Value(" not in content:
        return None
    name = _first_group(content, r"\$\{([^}:\s]+)(?::[^}]*)?}") or _effective_path(changed_file)
    return RuleMatch("CONFIG", "CONFIG_KEY", name, "Detected @Value config key change", "VALUE_CONFIG_HEURISTIC_RULE")


def _content_of(changed_file: dict[str, Any], global_diff_text: str | None) -> str:
    path = _effective_path(changed_file)
    diff = changed_file.get("diffText") or changed_file.get("diff") or changed_file.get("patch")
    return f"{path}\n{diff if diff else global_diff_text or ''}"


def _effective_path(changed_file: dict[str, Any]) -> str:
    return changed_file.get("path") or changed_file.get("newPath") or changed_file.get("new_path") or changed_file.get("oldPath") or changed_file.get("old_path") or "__unknown__"


def _change_type(changed_file: dict[str, Any]) -> str:
    return (changed_file.get("changeType") or changed_file.get("change_type") or "UNKNOWN").upper()


def _contains_any(value: str | None, keywords: list[str]) -> bool:
    normalized = (value or "").lower()
    return any(keyword.lower() in normalized for keyword in keywords)


def _path_matches(changed_file: dict[str, Any], keywords: list[str]) -> bool:
    return _contains_any(_effective_path(changed_file), keywords)


def _first_group(value: str, pattern: str) -> str | None:
    match = re.search(pattern, value or "", re.I | re.S)
    return match.group(1) if match else None


def _table_name(content: str, changed_file: dict[str, Any]) -> str:
    return _first_group(content, r"(?:from|into|update|table|join)\s+[`\"]?([a-zA-Z_][a-zA-Z0-9_]*)[`\"]?") or _effective_path(changed_file)


def _append_type(items: list[str], change_type: str) -> None:
    if change_type not in items:
        items.append(change_type)


def _sort_types(items: list[str]) -> list[str]:
    order = {value: index for index, value in enumerate(CHANGE_TYPE_ORDER)}
    return sorted(dict.fromkeys(items), key=lambda item: order.get(item, 999))


def _evidence(change_type: str, changed_file: dict[str, Any], snippet: str, matcher: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", snippet.strip())
    if len(compact) > 180:
        compact = compact[:177] + "..."
    return {
        "changeType": change_type,
        "filePath": _effective_path(changed_file),
        "lineStart": None,
        "lineEnd": None,
        "snippet": compact,
        "matcher": matcher,
    }


def _summary(changed_file_count: int, change_types: list[str]) -> str:
    if changed_file_count == 0:
        return "No changed files were provided."
    if not change_types:
        return f"Analyzed {changed_file_count} changed file(s); no MVP change type matched."
    return f"Analyzed {changed_file_count} changed file(s); matched change types: {', '.join(change_types)}."

