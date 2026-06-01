# 提醒卡片 JSON Schema

> 状态说明：JSON 字段仍沿用 `riskCard` / `riskItems` / `riskLevel` 命名；前端与钉钉展示层统一称“提醒卡片 / 提醒项”。权威结构以 `backend-python/app/risk_engine/service.py` 输出和本文件 JSON Schema 为准。

## 1. 设计目标

提醒卡片是规则提醒链路的统一输出对象，必须同时服务前端渲染、钉钉推送、数据库存储和后续人工反馈回流。钉钉消息只是 RiskCard 的展示转换结果，权威数据始终以 RiskCard JSON 为准。

当前文档以代码中的 `RiskCard` / `RiskItem` 结构为准，避免文档 schema 和实际落库 JSON 脱节。

## 2. 当前顶层结构

```json
{
  "cardId": "risk-card-10001",
  "summary": "本次变更涉及 API, DB_SQL，生成 2 个风险项，整体风险等级为 HIGH。",
  "riskLevel": "HIGH",
  "affectedResources": [],
  "focusIndicators": [],
  "riskItems": [],
  "recommendedChecks": [],
  "suggestedReviewRoles": [],
  "generatedAt": "2026-04-22T16:00:00+08:00",
  "generator": "risk-engine-rule-v1"
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `cardId` | string | 是 | 风险卡片唯一标识 |
| `summary` | string | 是 | 风险摘要 |
| `riskLevel` | enum | 是 | 整体风险等级 |
| `affectedResources` | array | 是 | 本次变更影响的资源集合 |
| `riskItems` | array | 是 | 风险项集合 |
| `recommendedChecks` | array | 是 | 汇总后的推荐检查项 |
| `suggestedReviewRoles` | array | 是 | 汇总后的建议 reviewer 角色 |
| `generatedAt` | string | 是 | 生成时间，ISO offset date-time |
| `generator` | string | 是 | 生成器标识 |

## 3. DB 细分规则输出要求

DB / CACHE / MQ 细分后，风险卡片必须优先展示细分类型，而不是只展示粗粒度 `DB`、`CACHE` 或 `MQ`。

### 3.1 changeType

`changeType` 用于变更分析结果、证据和风险分类。当前枚举：

```json
[
  "API",
  "DB",
  "DB_DATA_WRITE",
  "DB_SCHEMA",
  "DB_SQL",
  "ORM_MAPPING",
  "ENTITY_MODEL",
  "DATA_MIGRATION",
  "CACHE",
  "CACHE_WRITE_DELETE",
  "CACHE_KEY",
  "CACHE_TTL",
  "CACHE_INVALIDATION",
  "CACHE_READ_WRITE",
  "CACHE_SERIALIZATION",
  "MQ",
  "MQ_CONFIG",
  "MQ_PRODUCER",
  "MQ_CONSUMER",
  "MQ_MESSAGE_SCHEMA",
  "MQ_TOPIC_CONFIG",
  "MQ_RETRY_DLQ",
  "CONFIG"
]
```

约定：

- `DB` 是聚合兼容类型，不应作为细粒度风险项的首选展示类型。
- `DB_DATA_WRITE` 是默认模板收敛后的 DB 提醒类型，覆盖 DDL、写入 SQL、Entity 与 ORM 映射维护信号。
- `DB_SCHEMA` 表示明确 DDL / migration schema 变更。
- `DB_SQL` 表示 SQL 读写逻辑变更。
- `ORM_MAPPING` 表示 MyBatis / ORM 映射变更。
- `ENTITY_MODEL` 表示实体模型字段或 ORM 注解变更。
- `DATA_MIGRATION` 表示数据修复、回填或历史数据迁移风险。
- `CACHE` 是缓存聚合兼容类型，细分风险项优先使用 `CACHE_WRITE_DELETE` 或 `CACHE_KEY` / `CACHE_TTL` / `CACHE_INVALIDATION` / `CACHE_READ_WRITE` / `CACHE_SERIALIZATION`。
- `CACHE_WRITE_DELETE` 是默认模板收敛后的缓存提醒类型，覆盖 set/expire/delete/evict 等写入或失效信号。
- `MQ` 是消息队列聚合兼容类型，细分风险项优先使用 `MQ_CONFIG` 或 `MQ_PRODUCER` / `MQ_CONSUMER` / `MQ_MESSAGE_SCHEMA` / `MQ_TOPIC_CONFIG` / `MQ_RETRY_DLQ`。
- `MQ_CONFIG` 是默认模板收敛后的 MQ 提醒类型，覆盖 queue / exchange / routeKey 配置维护信号。

### 3.2 riskItem 扩展字段

DB 细分风险项必须携带以下解释字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `category` | changeType | 是 | 风险细分类型，DB / CACHE / MQ 相关优先使用细分类型 |
| `confidence` | enum 或 null | 否 | 规则置信度，当前使用 `LOW` / `MEDIUM` / `HIGH` |
| `reason` | string 或 null | 否 | 命中原因，应说明为什么判定该风险 |
| `relatedSignals` | array | 是 | 组合风险关联信号，例如 `entity model changed`、`migration or DDL not detected` |
| `evidences` | array | 是 | 命中的文件、片段和规则 |
| `maintenanceArtifacts` | array | 是 | 可复制维护产物，例如 SQL、Redis 命令、MQ 配置伪代码、Nacos 配置 |

前端展示要求：

- 风险项标题区域展示 `riskLevel`、`category`、`confidence`。
- 风险项详情展示 `reason`。
- 有 `relatedSignals` 时展示为标签。
- `evidences` 至少展示文件路径、matcher 和 snippet。
- DB 组合风险必须让用户能看出“由哪些信号组合而来”。
- DB / Redis / MQ / Nacos 配置等重点提醒应优先展示 `maintenanceArtifacts`；`confidence=EXACT` 表示直接来自 diff，`confidence=INFERRED` 表示由实体、映射或代码片段推断，需要人工确认后使用。
- DB 推断维护产物按表拆分：新增 Entity + `@TableName` 输出 `CREATE TABLE` 草稿，已有 Entity / Mapper 字段变更输出 `ALTER TABLE` 草稿；同表存在真实 DDL 时优先展示真实 SQL。

## 4. JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/risk-card.schema.json",
  "title": "RiskCard",
  "type": "object",
  "required": [
    "cardId",
    "summary",
    "riskLevel",
    "affectedResources",
    "focusIndicators",
    "riskItems",
    "recommendedChecks",
    "suggestedReviewRoles",
    "generatedAt",
    "generator"
  ],
  "properties": {
    "cardId": { "type": "string" },
    "summary": { "type": "string" },
    "riskLevel": { "$ref": "#/$defs/riskLevel" },
    "affectedResources": {
      "type": "array",
      "items": { "$ref": "#/$defs/impactedResource" }
    },
    "focusIndicators": {
      "type": "array",
      "items": { "$ref": "#/$defs/focusIndicator" }
    },
    "riskItems": {
      "type": "array",
      "items": { "$ref": "#/$defs/riskItem" }
    },
    "recommendedChecks": {
      "type": "array",
      "items": { "type": "string" }
    },
    "suggestedReviewRoles": {
      "type": "array",
      "items": { "$ref": "#/$defs/reviewRole" },
      "uniqueItems": true
    },
    "generatedAt": { "type": "string", "format": "date-time" },
    "generator": { "type": "string" }
  },
  "$defs": {
    "focusIndicator": {
      "type": "object",
      "required": [
        "code",
        "name",
        "riskLevel",
        "matched",
        "reason",
        "evidences",
        "sourceChangeTypes"
      ],
      "properties": {
        "code": {
          "type": "string",
          "enum": [
            "DB_SCHEMA_CHANGE",
            "MQ_CONFIG_CHANGE",
            "REDIS_CONFIG_CHANGE",
            "VALUE_CONFIG_CHANGE"
          ]
        },
        "name": { "type": "string" },
        "riskLevel": {
          "anyOf": [
            { "$ref": "#/$defs/riskLevel" },
            { "type": "null" }
          ]
        },
        "matched": { "type": "boolean" },
        "reason": { "type": "string" },
        "evidences": {
          "type": "array",
          "items": { "$ref": "#/$defs/riskEvidence" }
        },
        "sourceChangeTypes": {
          "type": "array",
          "items": { "$ref": "#/$defs/changeType" },
          "uniqueItems": true
        }
      }
    },
    "riskItem": {
      "type": "object",
      "required": [
        "riskId",
        "ruleCode",
        "category",
        "riskLevel",
        "title",
        "description",
        "affectedResources",
        "evidences",
        "recommendedChecks",
        "suggestedReviewRoles",
        "relatedSignals",
        "maintenanceArtifacts"
      ],
      "properties": {
        "riskId": { "type": "string" },
        "ruleCode": { "type": "string" },
        "category": { "$ref": "#/$defs/changeType" },
        "riskLevel": { "$ref": "#/$defs/riskLevel" },
        "title": { "type": "string" },
        "description": { "type": "string" },
        "impact": { "type": ["string", "null"] },
        "affectedResources": {
          "type": "array",
          "items": { "$ref": "#/$defs/impactedResource" }
        },
        "evidences": {
          "type": "array",
          "items": { "$ref": "#/$defs/riskEvidence" }
        },
        "recommendedChecks": {
          "type": "array",
          "items": { "type": "string" }
        },
        "suggestedReviewRoles": {
          "type": "array",
          "items": { "$ref": "#/$defs/reviewRole" },
          "uniqueItems": true
        },
        "confidence": { "type": ["string", "null"], "enum": ["LOW", "MEDIUM", "HIGH", null] },
        "reason": { "type": ["string", "null"] },
        "relatedSignals": {
          "type": "array",
          "items": { "type": "string" }
        },
        "maintenanceArtifacts": {
          "type": "array",
          "items": { "$ref": "#/$defs/maintenanceArtifact" }
        }
      }
    },
    "maintenanceArtifact": {
      "type": "object",
      "required": [
        "artifactType",
        "title",
        "language",
        "content",
        "confidence",
        "copyable",
        "sourceFilePath",
        "sourceChangeType",
        "notes"
      ],
      "properties": {
        "artifactType": {
          "type": "string",
          "enum": ["SQL", "REDIS_COMMAND", "MQ_CONFIG_CODE", "NACOS_CONFIG"]
        },
        "title": { "type": "string" },
        "language": {
          "type": "string",
          "enum": ["sql", "text", "java", "yaml", "properties"]
        },
        "content": { "type": "string" },
        "confidence": {
          "type": "string",
          "enum": ["EXACT", "INFERRED"]
        },
        "copyable": { "type": "boolean" },
        "sourceFilePath": { "type": ["string", "null"] },
        "sourceChangeType": { "$ref": "#/$defs/changeType" },
        "notes": { "type": "string" }
      }
    },
    "impactedResource": {
      "type": "object",
      "required": ["resourceType", "name"],
      "properties": {
        "resourceType": { "$ref": "#/$defs/resourceType" },
        "name": { "type": "string" },
        "operation": { "type": ["string", "null"] },
        "filePath": { "type": ["string", "null"] },
        "evidence": {
          "anyOf": [
            { "$ref": "#/$defs/changeEvidence" },
            { "type": "null" }
          ]
        }
      }
    },
    "riskEvidence": {
      "type": "object",
      "required": ["filePath"],
      "properties": {
        "filePath": { "type": "string" },
        "lineStart": { "type": ["integer", "null"], "minimum": 1 },
        "lineEnd": { "type": ["integer", "null"], "minimum": 1 },
        "snippet": { "type": ["string", "null"] },
        "matcher": { "type": ["string", "null"] }
      }
    },
    "changeEvidence": {
      "allOf": [
        { "$ref": "#/$defs/riskEvidence" },
        {
          "type": "object",
          "required": ["changeType"],
          "properties": {
            "changeType": { "$ref": "#/$defs/changeType" }
          }
        }
      ]
    },
    "changeType": {
      "type": "string",
      "enum": [
        "API",
        "DB",
        "DB_DATA_WRITE",
        "DB_SCHEMA",
        "DB_SQL",
        "ORM_MAPPING",
        "ENTITY_MODEL",
        "DATA_MIGRATION",
        "CACHE",
        "CACHE_WRITE_DELETE",
        "CACHE_KEY",
        "CACHE_TTL",
        "CACHE_INVALIDATION",
        "CACHE_READ_WRITE",
        "CACHE_SERIALIZATION",
        "MQ",
        "MQ_CONFIG",
        "MQ_PRODUCER",
        "MQ_CONSUMER",
        "MQ_MESSAGE_SCHEMA",
        "MQ_TOPIC_CONFIG",
        "MQ_RETRY_DLQ",
        "CONFIG"
      ]
    },
    "resourceType": {
      "type": "string",
      "enum": [
        "API",
        "DB_TABLE",
        "SQL",
        "ORM_MAPPING",
        "ENTITY_FIELD",
        "DATA_MIGRATION",
        "CACHE_KEY",
        "CACHE_POLICY",
        "CACHE_VALUE",
        "MQ_TOPIC",
        "MQ_PRODUCER",
        "MQ_CONSUMER",
        "MQ_MESSAGE",
        "CONFIG_KEY",
        "FILE"
      ]
    },
    "riskLevel": {
      "type": "string",
      "enum": ["NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },
    "reviewRole": {
      "type": "string",
      "enum": ["BACKEND", "FRONTEND", "DBA", "QA", "SRE", "ARCHITECT", "OWNER"]
    }
  }
}
```

## 5. DB 细分风险项示例

### 5.1 SQL 读写逻辑变更

```json
{
  "riskId": "RISK-DB_SQL-10001-001",
  "ruleCode": "DB_SQL_CHANGE_CHECK",
  "category": "DB_SQL",
  "riskLevel": "MEDIUM",
  "title": "SQL 读写逻辑变更需要确认性能与结果兼容",
  "description": "检测到 Mapper XML 或 SQL 文件中的 select/insert/update/delete 逻辑发生变化。",
  "impact": "可能导致查询结果变化、索引失效、慢 SQL 或写入逻辑异常。",
  "affectedResources": [
    {
      "resourceType": "DB_TABLE",
      "name": "car",
      "operation": "MODIFIED",
      "filePath": "src/main/resources/mapper/CarMapper.xml"
    }
  ],
  "evidences": [
    {
      "filePath": "src/main/resources/mapper/CarMapper.xml",
      "lineStart": null,
      "lineEnd": null,
      "snippet": "Detected SQL read/write logic change | car",
      "matcher": "DB_HEURISTIC_RULE"
    }
  ],
  "recommendedChecks": [
    "确认 where/join/order by/limit 变化是否影响结果集和性能。",
    "对核心查询补充执行计划或回归用例。"
  ],
  "suggestedReviewRoles": ["BACKEND", "DBA", "QA"],
  "confidence": "MEDIUM",
  "reason": "出现 SQL select/insert/update/delete 信号，但未直接发现表结构变更。",
  "relatedSignals": [],
  "maintenanceArtifacts": [
    {
      "artifactType": "SQL",
      "title": "可维护 SQL 片段",
      "language": "sql",
      "content": "select id, status from orders where id = #{id};",
      "confidence": "EXACT",
      "copyable": true,
      "sourceFilePath": "src/main/resources/mapper/OrderMapper.xml",
      "sourceChangeType": "DB_SQL",
      "notes": "从本次 diff 新增 SQL 行提取，执行前仍需确认执行计划和索引。"
    }
  ]
}
```

### 5.2 疑似数据库结构未同步

```json
{
  "riskId": "RISK-DB_SCHEMA_SYNC_SUSPECT-10001-001",
  "ruleCode": "DB_SCHEMA_SYNC_SUSPECT_CHECK",
  "category": "DB_SCHEMA",
  "riskLevel": "HIGH",
  "title": "疑似实体、映射与数据库结构未同步",
  "description": "检测到实体字段与 ORM/MyBatis 映射同时变化，但未检测到 migration 或 DDL。",
  "impact": "可能导致运行时字段不存在、写入失败、查询缺字段或线上表结构不一致。",
  "affectedResources": [],
  "evidences": [],
  "recommendedChecks": [
    "确认是否需要新增或修改 migration。",
    "如确实不需要 migration，请在 MR 说明中解释原因。"
  ],
  "suggestedReviewRoles": ["BACKEND", "DBA", "QA"],
  "confidence": "MEDIUM",
  "reason": "组合信号：entity model changed + ORM mapping changed + migration/DDL not detected。",
  "relatedSignals": [
    "entity model changed",
    "ORM/MyBatis mapping changed",
    "migration or DDL not detected"
  ],
  "maintenanceArtifacts": [
    {
      "artifactType": "SQL",
      "title": "待补数据库变更草稿",
      "language": "sql",
      "content": "-- INFERRED: 请确认表名、字段类型、默认值、索引和回滚脚本。\nALTER TABLE <table_name> ADD COLUMN support_device_model varchar(255) NULL;",
      "confidence": "INFERRED",
      "copyable": true,
      "sourceFilePath": "src/main/java/com/demo/car/entity/Car.java",
      "sourceChangeType": "DB_SCHEMA",
      "notes": "该 SQL 由实体字段或 ORM/MyBatis 映射推断生成，请人工确认后使用。"
    }
  ]
}
```

## 6. 钉钉推送转换规则

规则提醒钉钉消息以 Markdown 发送，标题固定为「变更提醒」。正文按 DB / MQ / Redis/缓存 / 配置分组展示简要提醒，并附带平台详情链接（`PLATFORM_BASE_URL/tasks/{taskId}`）；不再额外展示 GitLab 链接。

AI Review 完成后的钉钉消息标题为「代码质量 Review」，正文包含 provider、状态、等级、问题数、摘要、最多 5 条主要 finding 与平台详情链接；多模型任务链接可追加 `?reviewKey={reviewKey}`。

详细通知行为见 `03-api-contract.md` §6。
