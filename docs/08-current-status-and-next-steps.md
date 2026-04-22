# 当前进度状态与下一步计划

## 1. 当前结论

当前项目已经从纯设计文档推进到一个可演示的 MVP 原型。主链路已经具备基本形态：

```text
mock GitLab MR webhook
  -> 创建项目与审查任务
  -> 保存原始 webhook payload
  -> 变更分析
  -> 风险规则引擎
  -> 风险卡片生成
  -> 审查结果落库
  -> 钉钉推送或跳过记录
  -> 前端查看任务与风险卡片
```

但当前仍更接近“可演示版本”，还不是“稳定可接入真实研发流程的 MVP”。P0 本地闭环已验证通过，P1 已完成真实 GitLab MR diff/change 拉取联调；当前在没有 GitLab webhook 权限的情况下，先通过本地令牌和 `projectId + mrIid` 验证真实 MR 审查链路，后续拿到 webhook 权限后再切换为 GitLab 自动触发。

## 2. 已完成内容

### 2.1 文档与设计

已完成 MVP 设计文档：

- `00-product-overview.md`
- `01-architecture.md`
- `02-domain-model.md`
- `03-api-contract.md`
- `04-risk-card-schema.md`
- `05-mvp-roadmap.md`
- `06-change-analysis-rules.md`
- `07-risk-card-example.json`

覆盖内容包括产品定位、架构设计、领域模型、API 契约、风险卡片 schema、实施路线、变更分析规则和风险卡片示例。

### 2.2 后端基础工程

已完成 Spring Boot 后端基础骨架：

- Spring Boot Maven 工程。
- MySQL 数据源配置。
- Flyway 数据库 migration。
- 统一响应结构 `ApiResponse`。
- 统一异常处理 `GlobalExceptionHandler`。
- 请求 traceId。
- CORS 配置。
- 健康检查接口 `/api/health`。

### 2.3 数据库结构

已通过 migration 建立 MVP 基础表：

- `projects`
- `review_tasks`
- `review_results`
- `rule_templates`
- `notification_records`
- `notification_webhooks`
- `gitlab_mr_webhook_events`

已初始化模板：

- `backend-default`
- `frontend-default`
- `general-default`

### 2.4 GitLab MR webhook 最小链路

已实现：

- `POST /api/webhooks/gitlab/merge-request`
- 校验 MR webhook 基础字段。
- 解析项目、MR、分支、作者、changed files 摘要和事件时间。
- 自动 upsert 项目。
- 创建审查任务。
- 保存原始 webhook payload。

当前 webhook 链路支持两种输入：

- mock payload 中直接携带 `changedFiles` 与 `diffText`。
- 真实 GitLab MR webhook 不携带 `changedFiles` 时，通过 GitLab API 按 `projectId + mrIid` 拉取 MR diff。
- 兼容 GitLab 14.x：`/merge_requests/{iid}/diffs` 返回 404 时，自动 fallback 到 `/merge_requests/{iid}/changes`。

### 2.5 变更分析器

已实现 MVP 启发式变更分析器，支持识别：

- `API`
- `DB`
- `CACHE`
- `MQ`
- `CONFIG`

分析结果对象包括：

- `summary`
- `changedFileCount`
- `changeTypes`
- `changedFiles`
- `impactedResources`
- `evidences`

已提供单元测试覆盖常见示例。

### 2.6 风险规则引擎与风险卡片

已实现：

- 风险等级：`LOW / MEDIUM / HIGH / CRITICAL`。
- 默认风险规则配置文件 `risk-rules.json`。
- 根据变更分析结果生成风险项。
- 根据最高风险项计算整体风险等级。
- 生成结构化 `RiskCard`。

风险卡片包含：

- `summary`
- `riskLevel`
- `affectedResources`
- `riskItems`
- `recommendedChecks`
- `suggestedReviewRoles`

### 2.7 审查模板能力

已支持三套模板：

| 模板 | 场景 | 当前启用规则 |
| --- | --- | --- |
| `backend-default` | 后端项目 | API、DB、CACHE、MQ、CONFIG |
| `frontend-default` | 前端项目 | API、CONFIG |
| `general-default` | 通用项目 | API、DB、CONFIG |

已支持：

- 模板决定启用哪些规则。
- 模板定义推荐检查项。
- 项目绑定默认模板。
- 手动审查时指定模板。
- 前端查看模板与修改项目默认模板。

### 2.8 钉钉通知

已实现：

- 钉钉 webhook 推送器。
- 风险卡片 Markdown 格式化。
- 分析完成后自动推送。
- `DINGTALK_WEBHOOK_URL` 为空时记录 `SKIPPED`，不阻断主链路。
- 推送结果保存到 `notification_records`。

### 2.9 前端页面

已实现 React + Ant Design 最小管理页面：

- 任务列表页。
- 任务详情页。
- 风险卡片展示。
- 分析结果展示。
- 原始事件摘要展示。
- 模板配置页。
- 项目默认模板绑定。

## 3. 当前可以验证的能力

### 3.1 后端健康检查

```powershell
curl http://localhost:8080/api/health
curl http://localhost:8080/actuator/health
```

### 3.2 mock GitLab webhook 主链路

可以使用 README 中的 mock payload 验证：

```text
webhook -> task -> analysis -> risk card -> notification record -> query API -> frontend detail
```

### 3.3 任务查询

```powershell
curl http://localhost:8080/api/review-tasks
curl http://localhost:8080/api/review-tasks/1
curl http://localhost:8080/api/review-tasks/1/result
```

### 3.4 模板查询与绑定

```powershell
curl http://localhost:8080/api/rule-templates
curl http://localhost:8080/api/rule-templates/backend-default
curl http://localhost:8080/api/projects
```

项目默认模板绑定：

```powershell
Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8080/api/projects/1/default-template" `
  -ContentType "application/json" `
  -Body '{"templateCode":"frontend-default"}'
```

### 3.5 手动审查后端接口

```powershell
POST /api/review-tasks/manual
```

当前后端已支持，但前端还没有对应表单页面。

### 3.6 前端页面

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

访问：

```text
http://localhost:5173
```

可验证任务列表、任务详情、风险卡片、分析结果、原始事件和模板配置。

### 3.7 自动化测试

后端：

```powershell
cd backend
mvn -q test
```

前端构建：

```powershell
cd frontend
npm.cmd run build
```

### 3.8 本地启动脚本与 GitLab 联调脚本

已补充 Windows 启动脚本：

```powershell
.\scripts\run-backend.cmd
.\scripts\run-frontend.cmd
```

后端脚本会优先使用仓库本地 `tools/jdk-21`，并自动加载 `.local/gitlab.env`。前端脚本会在缺少 `node_modules` 时自动执行 `npm install`。

已补充 GitLab 真实 MR 联调脚本：

```powershell
.\scripts\verify-gitlab-diff.cmd
```

配置文件使用 `.local/gitlab.env`，示例见 `examples/gitlab.env.example`。`.local/` 已加入 `.gitignore`，用于保存 token、MySQL 密码等本地敏感配置。

### 3.9 已完成的真实 GitLab 验证

当前已在真实 GitLab MR 上验证通过：

```text
GitLab 14.5.0
internal projectId + mrIid
/diffs 返回 404
/changes fallback 返回 7 个变更文件
webhook 模拟请求创建审查任务
任务状态 SUCCESS
changedFilesSummary.source = gitlab_api
changedFilesSummary.count = 7
riskLevel = HIGH
riskItemCount = 1
changeTypes = DB
前端可查看该 MR 生成的 review 内容
```

## 4. 未完成或部分完成内容

### 4.1 真实 GitLab diff 拉取已完成联调，仍需 webhook 权限接入

已完成：

- 配置 GitLab base URL。
- 配置 GitLab token。
- 根据 `projectId + mrIid` 调用 GitLab MR diffs API。
- GitLab 14.x `/diffs` 404 时 fallback 到 MR changes API。
- payload 不含 changed files 时自动补拉。
- 拉取失败时任务标记 `FAILED` 并记录错误。
- 保留 P0 mock payload 优先逻辑。
- 补充 GitLab client 和 webhook service 单元测试。
- 使用真实 GitLab 项目和真实 token 完成令牌联调。

仍需补齐：

- GitLab webhook 权限开通后，配置真实 MR webhook 自动触发。
- 项目级 GitLab base URL / token 配置。
- GitLab API 失败重试与更细粒度错误记录。
- 对超大 diff、`collapsed`、`too_large` 文件做更明确的处理策略。

### 4.2 Jenkins 入口未完成

当前还没有：

- Jenkins webhook controller。
- 构建成功后触发审查。
- 发布前触发审查。

MVP 当前仍以 GitLab webhook 和手动审查为主。

### 4.3 前端手动发起审查页面未完成

后端已有 `POST /api/review-tasks/manual`，但前端缺少表单页面。

建议页面支持：

- 选择项目。
- 选择模板。
- 填写 sourceBranch / targetBranch。
- 粘贴 changed files JSON 或 diff 文本。
- 发起审查后跳转任务详情页。

### 4.4 钉钉项目级配置未完成

虽然已有 `notification_webhooks` 表，但当前实际推送仍主要依赖环境变量：

```text
DINGTALK_WEBHOOK_URL
```

后续需要：

- 项目绑定钉钉 webhook 配置。
- 从数据库读取项目通知配置。
- 支持密钥签名。
- 前端展示和配置通知目标。
- 推送失败重试策略。

### 4.5 集成测试不足

当前已有变更分析器和风险引擎单元测试，但缺少主链路集成测试。

应补充：

```text
webhook -> task -> analysis -> risk card -> notification record -> query result
```

验收点：

- webhook 返回成功。
- `review_tasks` 有记录。
- `review_results` 有分析结果和风险卡片。
- `notification_records` 有 `SKIPPED` 或 `SUCCESS` 记录。
- `/api/review-tasks/{id}/result` 能返回风险卡片。

### 4.6 README 和 demo 数据需要整理

README 已包含大量启动和联调说明，但存在早期状态描述和当前进度不一致的问题。建议单独整理。

建议新增：

```text
examples/gitlab-mr-webhook.json
examples/manual-review-request.json
examples/README.md
```

并补充常见错误排查：

- webhook 返回 400。
- MySQL 连接失败。
- Flyway migration 报错。
- 钉钉 webhook 未配置。
- 前端代理失败。

### 4.7 RiskCard schema 与当前对象需进一步对齐

`docs/04-risk-card-schema.md` 中的 schema 更完整，当前后端 `RiskCard` 是 MVP 简化对象。

后续需要二选一：

1. 让代码输出完全贴合 `docs/04-risk-card-schema.md`。
2. 更新 schema，明确当前 MVP 简化版字段。

建议在 MVP 阶段优先做字段对齐，避免前端、钉钉和数据库里出现多个风险卡片口径。

### 4.8 知识库与人工反馈未完成

当前 `knowledge-base` 仍是 placeholder。

尚未支持：

- 人工确认风险项。
- 忽略/采纳建议。
- Review 反馈回流。
- 历史相似问题提示。
- 团队知识沉淀。

## 5. 下一步推荐优先级

### P0：稳定当前主链路

目标：让当前 mock 输入下的完整闭环稳定可验证。

当前状态：

- 已验证本地 P0 链路：mock webhook -> analysis -> risk card -> review result -> frontend。
- 已验证前后端代理链路。

后续建议任务：

1. 清理 README 旧描述。
2. 新增 `examples/` demo payload。
3. 补主链路集成测试。
4. 明确本地验证步骤。

验收标准：

```text
启动 MySQL -> 启动后端 -> 启动前端 -> 发送 demo webhook -> 前端查看风险卡片
```

每一步都有稳定文档和可复制命令。

### P1：接真实 GitLab diff（最小实现已完成）

目标：从 mock changed files 走向真实 GitLab MR 接入。

已完成任务：

1. 新增 GitLab 配置：`GITLAB_BASE_URL`、`GITLAB_TOKEN`。
2. 实现 `GitLabClient`。
3. 根据 project id 和 MR iid 拉取 changed files / diff。
4. webhook payload 缺少 changed files 时自动拉取。
5. GitLab 14.x `/changes` fallback。
6. 补成功和失败测试。
7. 基于真实 GitLab MR 完成令牌联调。

验收标准：

- payload 不带 `changedFiles` 时，会调用 GitLab API 补拉 diff。
- 补拉成功后 `changedFilesSummary.source = gitlab_api`。
- GitLab API 未启用、配置缺失、接口失败或返回空 diff 时，任务会进入 `FAILED`。
- P0 mock payload 自带 `changedFiles` 时，不调用 GitLab API。

仍需真实环境验收：

- 使用真实 GitLab MR webhook 触发审查。
- 无需手动在 payload 中塞 `changedFiles`。
- `/api/review-tasks/{taskId}/result` 能返回基于真实 diff 生成的风险卡片。

当前限制：

- 暂无 GitLab webhook 配置权限，所以继续使用 `verify-gitlab-diff.cmd` 通过令牌和 `projectId + mrIid` 打通真实 MR 审查流程。
- 拿到管理员 webhook 权限后，再把触发方式从本地脚本切换到 GitLab 自动回调。

### P2：前端手动审查页面

目标：让 Web 平台具备手动发起审查入口。

建议任务：

1. 新增“手动审查”页面。
2. 支持选择项目和模板。
3. 支持填写 changed files JSON。
4. 支持填写全局 diff。
5. 发起后跳转任务详情。

验收标准：

- 不依赖 GitLab webhook，也能从前端创建审查任务并查看风险卡片。

### P3：钉钉配置入库

目标：从环境变量推送升级为项目级通知配置。

建议任务：

1. 使用 `notification_webhooks` 表。
2. 项目绑定 webhook 配置。
3. 推送时优先读取项目配置。
4. 前端增加通知配置展示。
5. 支持未配置时 SKIPPED。

验收标准：

- 不同项目可推送到不同钉钉群。

### P4：RiskCard schema 对齐

目标：统一文档、数据库、前端和钉钉使用的风险卡片结构。

建议任务：

1. 对齐 `docs/04-risk-card-schema.md` 与后端 `RiskCard`。
2. 补 schema 校验测试。
3. 前端基于统一 schema 渲染。

验收标准：

- 风险卡片 JSON 有唯一权威结构。

## 6. 建议的下一轮 Codex 任务

建议按以下顺序继续推进：

1. `请补一个 webhook 到 review result 的主链路集成测试，覆盖 mock payload 和 gitlab_api source。`
2. `请新增 examples 目录下的 mock GitLab webhook 和 manual review 请求示例。`
3. `请实现前端手动发起审查页面，支持输入 projectId + mrIid 或 changedFiles。`
4. `请在拿到 GitLab webhook 权限后，配置真实 webhook 并验证自动触发链路。`
5. `请把 GitLab token 和钉钉 webhook 从环境变量升级为项目级数据库配置。`

## 7. 暂缓事项

以下能力先不建议马上做：

- AI 增强审查。
- 知识库和历史相似问题。
- 人工反馈闭环。
- Jenkins 入口。
- 复杂权限体系。
- 规则模板完整在线编辑器。
- 统计看板。

这些都属于增强能力，应在主链路稳定、真实 GitLab diff 接入完成后再推进。
