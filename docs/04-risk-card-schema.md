# 风险卡片 JSON Schema

## 1. 设计目标

风险卡片是 MVP 的统一输出对象，必须同时服务前端渲染、钉钉推送、数据库存储和后续人工反馈回流。钉钉消息只是 RiskCard 的展示转换结果，权威数据始终以 RiskCard JSON 为准。

## 2. 顶层结构

```json
{
  "schemaVersion": "1.0",
  "cardId": "risk-card-10001",
  "taskId": "10001",
  "project": {},
  "trigger": {},
  "changeSummary": {},
  "impactScope": {},
  "riskSummary": {},
  "riskItems": [],
  "recommendedActions": [],
  "notification": {},
  "metadata": {}
}
```

## 3. JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/risk-card.schema.json",
  "title": "RiskCard",
  "type": "object",
  "required": [
    "schemaVersion",
    "cardId",
    "taskId",
    "project",
    "trigger",
    "changeSummary",
    "impactScope",
    "riskSummary",
    "riskItems",
    "recommendedActions",
    "metadata"
  ],
  "properties": {
    "schemaVersion": { "type": "string" },
    "cardId": { "type": "string" },
    "taskId": { "type": "string" },
    "project": { "$ref": "#/$defs/project" },
    "trigger": { "$ref": "#/$defs/trigger" },
    "changeSummary": { "$ref": "#/$defs/changeSummary" },
    "impactScope": { "$ref": "#/$defs/impactScope" },
    "riskSummary": { "$ref": "#/$defs/riskSummary" },
    "riskItems": {
      "type": "array",
      "items": { "$ref": "#/$defs/riskItem" }
    },
    "recommendedActions": {
      "type": "array",
      "items": { "$ref": "#/$defs/recommendedAction" }
    },
    "notification": { "$ref": "#/$defs/notification" },
    "metadata": { "$ref": "#/$defs/metadata" }
  },
  "$defs": {
    "project": {
      "type": "object",
      "required": ["projectId", "name", "gitProvider"],
      "properties": {
        "projectId": { "type": "string" },
        "name": { "type": "string" },
        "gitProvider": { "type": "string", "enum": ["GITLAB"] },
        "repositoryUrl": { "type": ["string", "null"] }
      }
    },
    "trigger": {
      "type": "object",
      "required": ["triggerType"],
      "properties": {
        "triggerType": {
          "type": "string",
          "enum": ["GITLAB_MR_WEBHOOK", "JENKINS", "MANUAL"]
        },
        "externalSourceId": { "type": ["string", "null"] },
        "externalUrl": { "type": ["string", "null"] },
        "sourceBranch": { "type": ["string", "null"] },
        "targetBranch": { "type": ["string", "null"] },
        "commitSha": { "type": ["string", "null"] },
        "author": {
          "type": "object",
          "properties": {
            "name": { "type": ["string", "null"] },
            "username": { "type": ["string", "null"] }
          }
        }
      }
    },
    "changeSummary": {
      "type": "object",
      "required": ["summaryText", "changedFileCount", "changeTypes", "changedFiles"],
      "properties": {
        "summaryText": { "type": "string" },
        "changedFileCount": { "type": "integer", "minimum": 0 },
        "changeTypes": {
          "type": "array",
          "items": { "$ref": "#/$defs/changeType" },
          "uniqueItems": true
        },
        "changedFiles": {
          "type": "array",
          "items": { "$ref": "#/$defs/changedFile" }
        }
      }
    },
    "impactScope": {
      "type": "object",
      "required": ["summary", "resources"],
      "properties": {
        "summary": { "type": "string" },
        "resources": {
          "type": "array",
          "items": { "$ref": "#/$defs/impactedResource" }
        }
      }
    },
    "riskSummary": {
      "type": "object",
      "required": ["overallLevel", "highestSeverity", "riskItemCount", "needsSpecialReview"],
      "properties": {
        "overallLevel": { "$ref": "#/$defs/riskLevel" },
        "highestSeverity": { "$ref": "#/$defs/riskLevel" },
        "riskItemCount": { "type": "integer", "minimum": 0 },
        "needsSpecialReview": { "type": "boolean" },
        "recommendedReviewerRoles": {
          "type": "array",
          "items": { "$ref": "#/$defs/ownerRole" },
          "uniqueItems": true
        }
      }
    },
    "changedFile": {
      "type": "object",
      "required": ["path", "changeType", "matchedChangeTypes"],
      "properties": {
        "path": { "type": "string" },
        "changeType": {
          "type": "string",
          "enum": ["ADDED", "MODIFIED", "DELETED", "RENAMED", "UNKNOWN"]
        },
        "language": { "type": ["string", "null"] },
        "matchedChangeTypes": {
          "type": "array",
          "items": { "$ref": "#/$defs/changeType" },
          "uniqueItems": true
        }
      }
    },
    "impactedResource": {
      "type": "object",
      "required": ["resourceType", "name", "evidence"],
      "properties": {
        "resourceType": {
          "type": "string",
          "enum": ["API", "DB_TABLE", "SQL", "CACHE_KEY", "MQ_TOPIC", "CONFIG_KEY", "FILE"]
        },
        "name": { "type": "string" },
        "operation": {
          "type": ["string", "null"],
          "enum": ["ADD", "MODIFY", "DELETE", "READ", "WRITE", "UNKNOWN", null]
        },
        "filePath": { "type": ["string", "null"] },
        "evidence": { "$ref": "#/$defs/evidence" }
      }
    },
    "riskItem": {
      "type": "object",
      "required": [
        "riskId",
        "category",
        "severity",
        "title",
        "description",
        "evidences",
        "suggestions",
        "checkItems",
        "source"
      ],
      "properties": {
        "riskId": { "type": "string" },
        "category": {
          "type": "string",
          "enum": ["API", "DB", "CACHE", "MQ", "CONFIG", "RELEASE", "OBSERVABILITY"]
        },
        "severity": { "type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"] },
        "title": { "type": "string" },
        "description": { "type": "string" },
        "impact": { "type": ["string", "null"] },
        "evidences": { "type": "array", "items": { "$ref": "#/$defs/evidence" } },
        "suggestions": { "type": "array", "items": { "type": "string" } },
        "checkItems": { "type": "array", "items": { "$ref": "#/$defs/checkItem" } },
        "ownerRoles": { "type": "array", "items": { "$ref": "#/$defs/ownerRole" } },
        "source": { "$ref": "#/$defs/riskSource" }
      }
    },
    "recommendedAction": {
      "type": "object",
      "required": ["actionId", "title", "priority"],
      "properties": {
        "actionId": { "type": "string" },
        "title": { "type": "string" },
        "description": { "type": ["string", "null"] },
        "priority": { "type": "string", "enum": ["LOW", "MEDIUM", "HIGH"] },
        "ownerRole": { "anyOf": [{ "$ref": "#/$defs/ownerRole" }, { "type": "null" }] }
      }
    },
    "notification": {
      "type": "object",
      "properties": {
        "dingtalkTitle": { "type": ["string", "null"] },
        "dingtalkMarkdown": { "type": ["string", "null"] }
      }
    },
    "metadata": {
      "type": "object",
      "required": ["templateCode", "generatedAt", "generator"],
      "properties": {
        "templateCode": { "type": "string" },
        "templateVersion": { "type": ["integer", "null"] },
        "generatedAt": { "type": "string", "format": "date-time" },
        "generator": { "type": "string" },
        "traceId": { "type": ["string", "null"] }
      }
    },
    "evidence": {
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
    "checkItem": {
      "type": "object",
      "required": ["text", "required"],
      "properties": {
        "text": { "type": "string" },
        "required": { "type": "boolean" }
      }
    },
    "riskSource": {
      "type": "object",
      "required": ["sourceType"],
      "properties": {
        "sourceType": { "type": "string", "enum": ["RULE", "AI", "MANUAL"] },
        "ruleCode": { "type": ["string", "null"] },
        "confidence": { "type": ["number", "null"], "minimum": 0, "maximum": 1 }
      }
    },
    "changeType": { "type": "string", "enum": ["API", "DB", "CACHE", "MQ", "CONFIG"] },
    "riskLevel": { "type": "string", "enum": ["NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"] },
    "ownerRole": { "type": "string", "enum": ["BACKEND", "FRONTEND", "DBA", "QA", "SRE", "ARCHITECT", "OWNER"] }
  }
}
```

## 4. 示例风险卡片

```json
{
  "schemaVersion": "1.0",
  "cardId": "risk-card-10001",
  "taskId": "10001",
  "project": {
    "projectId": "1",
    "name": "demo-service",
    "gitProvider": "GITLAB",
    "repositoryUrl": "https://gitlab.example.com/group/demo-service"
  },
  "trigger": {
    "triggerType": "GITLAB_MR_WEBHOOK",
    "externalSourceId": "12",
    "externalUrl": "https://gitlab.example.com/group/demo-service/-/merge_requests/12",
    "sourceBranch": "feature/risk-demo",
    "targetBranch": "main",
    "commitSha": "abcdef123456",
    "author": {
      "name": "Alice",
      "username": "alice"
    }
  },
  "changeSummary": {
    "summaryText": "本次 MR 修改了订单查询接口、订单 SQL 和订单缓存写入逻辑。",
    "changedFileCount": 3,
    "changeTypes": ["API", "DB", "CACHE"],
    "changedFiles": [
      {
        "path": "src/main/java/com/demo/order/OrderController.java",
        "changeType": "MODIFIED",
        "language": "Java",
        "matchedChangeTypes": ["API"]
      },
      {
        "path": "src/main/resources/mapper/OrderMapper.xml",
        "changeType": "MODIFIED",
        "language": "XML",
        "matchedChangeTypes": ["DB"]
      },
      {
        "path": "src/main/java/com/demo/order/OrderCacheService.java",
        "changeType": "MODIFIED",
        "language": "Java",
        "matchedChangeTypes": ["CACHE"]
      }
    ]
  },
  "impactScope": {
    "summary": "影响订单查询接口、orders 表查询 SQL 和 order:detail 缓存。",
    "resources": [
      {
        "resourceType": "API",
        "name": "GET /api/orders/{id}",
        "operation": "MODIFY",
        "filePath": "src/main/java/com/demo/order/OrderController.java",
        "evidence": {
          "filePath": "src/main/java/com/demo/order/OrderController.java",
          "lineStart": 42,
          "lineEnd": 48,
          "snippet": "@GetMapping(\"/api/orders/{id}\")",
          "matcher": "SpringMappingAnalyzer"
        }
      }
    ]
  },
  "riskSummary": {
    "overallLevel": "HIGH",
    "highestSeverity": "HIGH",
    "riskItemCount": 1,
    "needsSpecialReview": true,
    "recommendedReviewerRoles": ["BACKEND", "QA"]
  },
  "riskItems": [
    {
      "riskId": "RISK-API-10001-001",
      "category": "API",
      "severity": "HIGH",
      "title": "接口响应字段变更可能影响调用方兼容性",
      "description": "检测到订单查询接口相关 Controller 或 DTO 发生变化，需要确认是否删除、重命名或改变字段语义。",
      "impact": "可能导致前端或下游服务解析失败。",
      "evidences": [
        {
          "filePath": "src/main/java/com/demo/order/OrderController.java",
          "lineStart": 42,
          "lineEnd": 48,
          "snippet": "@GetMapping(\"/api/orders/{id}\")",
          "matcher": "API_COMPATIBILITY_CHECK"
        }
      ],
      "suggestions": [
        "确认接口响应字段是否保持向后兼容。",
        "如存在不兼容变更，需要补充版本兼容、灰度或调用方同步方案。"
      ],
      "checkItems": [
        {
          "text": "确认前端和下游调用方是否已适配。",
          "required": true
        },
        {
          "text": "补充接口契约测试或回归用例。",
          "required": true
        }
      ],
      "ownerRoles": ["BACKEND", "QA"],
      "source": {
        "sourceType": "RULE",
        "ruleCode": "API_COMPATIBILITY_CHECK",
        "confidence": 0.85
      }
    }
  ],
  "recommendedActions": [
    {
      "actionId": "ACTION-10001-001",
      "title": "安排接口兼容性专项 review",
      "description": "本次变更涉及接口，建议 reviewer 优先确认兼容性。",
      "priority": "HIGH",
      "ownerRole": "BACKEND"
    }
  ],
  "notification": {
    "dingtalkTitle": "demo-service MR !12 风险审查：HIGH",
    "dingtalkMarkdown": "### demo-service MR !12 风险审查\n\n整体风险：HIGH\n\n- 接口响应字段变更可能影响调用方兼容性"
  },
  "metadata": {
    "templateCode": "backend-default",
    "templateVersion": 1,
    "generatedAt": "2026-04-19T12:00:08+08:00",
    "generator": "risk-engine-rule-v1",
    "traceId": "20260419120000-demo"
  }
}
```

## 5. 钉钉推送转换规则

MVP 推荐将 RiskCard 转换为钉钉 Markdown：

- 标题：`${project.name} MR !${externalSourceId} 风险审查：${overallLevel}`。
- 摘要：展示 `changeSummary.summaryText`。
- 影响面：展示 `impactScope.summary`。
- 风险项：按严重级别降序列出 `title`、`severity`、`suggestions`。
- 行动项：展示 `recommendedActions` 中 HIGH / MEDIUM 优先级项。
- 链接：展示 MR 链接和平台任务详情链接。
