# 风险卡片 JSON Schema

## 1. 设计目标

风险卡片是 MVP 的统一输出对象，必须同时服务前端渲染、钉钉推送、数据库存储和后续人工反馈回流。钉钉消息只是 RiskCard 的展示转换结果，权威数据始终以 RiskCard JSON 为准。

当前文档以代码中的 `RiskCard` / `RiskItem` 结构为准，避免文档 schema 和实际落库 JSON 脱节。

## 2. 当前顶层结构

```json
{
  "cardId": "risk-card-10001",
  "summary": "本次变更涉及 API, DB_SQL，生成 2 个风险项，整体风险等级为 HIGH。",
  "riskLevel": "HIGH",
  "affectedResources": [],
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

DB 细分后，风险卡片必须优先展示细分类型，而不是只展示粗粒度 `DB`。

### 3.1 changeType

`changeType` 用于变更分析结果、证据和风险分类。当前枚举：

```json
[
  "API",
  "DB",
  "DB_SCHEMA",
  "DB_SQL",
  "ORM_MAPPING",
  "ENTITY_MODEL",
  "DATA_MIGRATION",
  "CACHE",
  "MQ",
  "CONFIG"
]
```

约定：

- `DB` 是聚合兼容类型，不应作为细粒度风险项的首选展示类型。
- `DB_SCHEMA` 表示明确 DDL / migration schema 变更。
- `DB_SQL` 表示 SQL 读写逻辑变更。
- `ORM_MAPPING` 表示 MyBatis / ORM 映射变更。
- `ENTITY_MODEL` 表示实体模型字段或 ORM 注解变更。
- `DATA_MIGRATION` 表示数据修复、回填或历史数据迁移风险。

### 3.2 riskItem 扩展字段

DB 细分风险项必须携带以下解释字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `category` | changeType | 是 | 风险细分类型，DB 相关优先使用 `DB_SCHEMA` / `DB_SQL` / `ORM_MAPPING` / `ENTITY_MODEL` / `DATA_MIGRATION` |
| `confidence` | enum 或 null | 否 | 规则置信度，当前使用 `LOW` / `MEDIUM` / `HIGH` |
| `reason` | string 或 null | 否 | 命中原因，应说明为什么判定该风险 |
| `relatedSignals` | array | 是 | 组合风险关联信号，例如 `entity model changed`、`migration or DDL not detected` |
| `evidences` | array | 是 | 命中的文件、片段和规则 |

前端展示要求：

- 风险项标题区域展示 `riskLevel`、`category`、`confidence`。
- 风险项详情展示 `reason`。
- 有 `relatedSignals` 时展示为标签。
- `evidences` 至少展示文件路径、matcher 和 snippet。
- DB 组合风险必须让用户能看出“由哪些信号组合而来”。

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
        "relatedSignals"
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
        }
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
        "DB_SCHEMA",
        "DB_SQL",
        "ORM_MAPPING",
        "ENTITY_MODEL",
        "DATA_MIGRATION",
        "CACHE",
        "MQ",
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
        "MQ_TOPIC",
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
  "relatedSignals": []
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
  ]
}
```

## 6. 钉钉推送转换规则

MVP 推荐将 RiskCard 转换为钉钉 Markdown：

- 标题：`${projectName} MR !${externalSourceId} 风险审查：${riskLevel}`。
- 摘要：展示 `summary`。
- 风险项：按严重级别列出 `title`、`riskLevel`、`category`、`confidence`。
- DB 细分风险项：展示 `reason` 和关键 `relatedSignals`。
- 推荐检查：展示 `recommendedChecks`。
- 链接：展示 MR 链接和平台任务详情链接。
