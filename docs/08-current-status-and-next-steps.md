# 当前进度状态与下一步计划

## 0. 给新对话的快速摘要

如果只想快速理解当前项目状态，请先看这一节。

当前已明确完成：

- P0 本地闭环已验证通过：`mock webhook -> analysis -> risk card -> 落库 -> 前端查看`。
- P1 真实 GitLab diff/change 拉取已联调通过：
  - 支持 payload 不带 `changedFiles` 时按 `projectId + mrIid` 拉取真实 MR diff。
  - 兼容 GitLab 14.x：`/diffs` 404 时 fallback 到 `/changes`。
- DB / MQ / CACHE 第一轮细粒度规则已实现。
- 风险卡片 schema、前端展示和对应测试已做第一轮对齐。

当前推荐优先级：

1. 先收口稳定性和可复现性，不继续优先扩规则。
2. 先补 `examples/` 示例数据和 README 验证说明。
3. 再补主链路集成测试，覆盖 `mock payload` 和 `gitlab_api source`。
4. 然后做钉钉细分展示、项目级配置。
5. 稳定性任务收口后，再继续推进 API 第一轮细粒度规则。

如果下一个对话只做一个小目标，优先建议：

```text
新增 examples/ 示例数据并清理 README 中的大段 payload，
然后补 webhook -> review_result -> notification_records 的主链路集成测试。
```
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

配置文件使用 `.local/gitlab.env`，示例见 `examples/gitlab.env.example`。`.local/` 已加入 `.gitignore`，用于保存 token、MySQL 密码等本地敏感配置。验证脚本会读取 GitLab project detail 和 MR detail，并校验后端创建的任务已使用真实项目名、真实 MR URL 和真实 source/target branch。

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

### 3.10 DB 规则精度优化第一轮已完成

当前风险识别仍是 MVP 启发式规则，但已完成第一轮 DB 细分优化，避免把 Mapper XML 或实体字段变更直接等同于数据库结构变更。

已完成：

- GitLab 扫描模式的数据准确性：用 MR detail / project detail API 填充真实项目名、MR URL、分支、作者和 commit sha。
- DB 风险细分：将单一 `DB` 拆为 `DB_SCHEMA`、`DB_SQL`、`ORM_MAPPING`、`ENTITY_MODEL`、`DATA_MIGRATION` 等更细类型，并保留 `DB` 作为聚合兼容类型。
- 置信度与证据：风险项已携带命中原因、证据文件、置信度，区分“明确 DDL/migration 变更”和“Mapper SQL/实体字段疑似影响”。
- 跨文件关联：实体类字段变更 + Mapper 映射变更 + 缺少 migration 时，会生成“疑似 DB schema 未同步”组合风险。
- 规则模板迁移：新增 `V4__db_fine_grained_rule_templates.sql`，将后端和通用模板升级到 DB 细分规则。

后续仍需优化：

- 前端风险卡片进一步突出展示 `confidence`、`reason`、`relatedSignals`。
- 与 `docs/04-risk-card-schema.md` 对齐，形成唯一权威 schema。
- 用真实业务 MR 持续校准规则误报和漏报。

#### 3.10.1 规则细分目标

第一轮不直接追求“所有规则都准确”，而是先把 DB 相关风险从粗粒度命中拆成可解释的最小规则集：

| 细分类型 | 含义 | 典型命中条件 | 初始置信度 |
| --- | --- | --- | --- |
| `DB_SCHEMA` | 数据库结构变更 | Flyway/Liquibase migration、DDL、`ALTER TABLE`、`CREATE TABLE`、`DROP COLUMN` | HIGH |
| `DB_SQL` | SQL 读写逻辑变更 | Mapper XML / SQL 文件中 `select`、`insert`、`update`、`delete`、where/join/order by 变化 | MEDIUM |
| `ORM_MAPPING` | ORM / MyBatis 映射变更 | `resultMap`、`@Column`、`@Table`、字段映射、Mapper 返回字段变化 | MEDIUM |
| `ENTITY_MODEL` | 实体模型字段变更 | Java entity / DO / PO 字段增删改、字段类型变化、序列化字段变化 | MEDIUM |
| `DATA_MIGRATION` | 数据迁移或历史数据兼容风险 | migration 中包含数据修复 SQL、默认值回填、枚举值/状态值转换 | HIGH |

#### 3.10.2 命中原则

规则实现时需要避免“看到 Mapper XML 就直接判定表结构风险”的误报：

- 只改 Mapper XML 的 SQL：优先命中 `DB_SQL`，不直接命中 `DB_SCHEMA`。
- 只改实体类字段：优先命中 `ENTITY_MODEL`，提示确认是否需要同步 DB/mapping，但不直接断言已发生表结构变更。
- 出现 DDL / migration：强命中 `DB_SCHEMA`。
- 实体字段变更 + Mapper 映射字段变更 + 没有 migration：生成“疑似 DB schema 未同步”组合风险，风险等级提升。
- Mapper 查询条件、join、order by、limit 变化：命中 `DB_SQL`，推荐检查索引、数据量、分页和执行计划。
- resultMap / insert / update 字段集合变化：命中 `ORM_MAPPING`，推荐检查字段兼容、空值、默认值和回归用例。

#### 3.10.3 风险输出字段规划

细粒度规则需要在风险卡片中增加或显式保留以下信息：

- `category`：细分类型，如 `DB_SQL`、`ENTITY_MODEL`。
- `confidence`：`LOW / MEDIUM / HIGH`。
- `reason`：为什么命中该风险。
- `evidences`：命中文件、片段、规则名。
- `relatedSignals`：组合判断时关联到的其他信号，例如 entity changed、mapper changed、migration missing。

MVP 兼容策略：当前已先把 `confidence`、`reason`、`relatedSignals` 放进 `riskItems`，后续再和 `docs/04-risk-card-schema.md` 做统一对齐。

#### 3.10.4 第一轮实现范围

第一轮只覆盖 DB 相关规则，不同时扩展 API/CACHE/MQ/CONFIG，已完成：

1. 更新 `docs/06-change-analysis-rules.md`，写清 DB 细分类型和命中样例。
2. 更新后端 `ChangeType` / 规则配置，支持 `DB_SCHEMA`、`DB_SQL`、`ORM_MAPPING`、`ENTITY_MODEL`、`DATA_MIGRATION`。
3. 调整变更分析器，输出细分类型和证据。
4. 调整风险规则引擎，为细分类型生成更准确的风险项和推荐检查项。
5. 补单元测试，覆盖 Mapper XML、entity 字段、migration、组合风险四类样例。

#### 3.10.5 验收样例

第一轮规则优化已满足：

- 仅修改 `CarMapper.xml` 查询 SQL：输出 `DB_SQL`，不输出 `DB_SCHEMA`。
- 修改 entity 字段但无 migration：输出 `ENTITY_MODEL`，并提示确认 DB/mapping 是否同步。
- 修改 Flyway migration DDL：输出 `DB_SCHEMA`，置信度 HIGH。
- 同时修改 entity 字段和 Mapper 映射但无 migration：输出组合风险“疑似 DB schema 未同步”，风险等级至少 HIGH。
- 风险卡片能展示命中原因和证据，前端不再只显示粗粒度 `DB`。

## 4. 未完成或部分完成内容

### 4.1 真实 GitLab diff 拉取已完成联调，仍需 webhook 权限接入

已完成：

- 配置 GitLab base URL。
- 配置 GitLab token。
- 根据 `projectId + mrIid` 调用 GitLab MR diffs API。
- GitLab 14.x `/diffs` 404 时 fallback 到 MR changes API。
- GitLab 扫描模式下使用 project detail / MR detail 回填真实项目信息和分支信息。
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

已完成一部分：

- 模板 `config_json.focusChangeTypes` 可控制钉钉关注标签。
- `backend-default` 默认只关注 `DB_SCHEMA`、`DATA_MIGRATION`、`ENTITY_MODEL`。
- 未命中关注标签时仍完整落库，但通知记录为 `SKIPPED`。

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
examples/gitlab-mr-webhook.mock.json
examples/gitlab-mr-webhook.real-no-changed-files.json
examples/manual-review-request.json
examples/README.md
```

并补充常见错误排查：

- webhook 返回 400。
- MySQL 连接失败。
- Flyway migration 报错。
- 钉钉 webhook 未配置。
- 前端代理失败。

### 4.7 RiskCard schema 第一轮已对齐

`docs/04-risk-card-schema.md` 已更新为当前后端 `RiskCard` / `RiskItem` 的实际结构，并明确 DB / MQ / CACHE 细分风险项的 `category`、`confidence`、`reason`、`relatedSignals`、`evidences` 展示要求。

已完成：

1. schema 文档对齐当前 MVP 简化版字段。
2. 前端风险卡片展示 DB / MQ / CACHE 细分类型、置信度、命中原因、关联信号和证据。
3. 后端 `RiskItem` 已输出 `confidence` / `reason` / `relatedSignals`。
4. 新增 `RiskCardSchemaTest`，解析 `docs/04-risk-card-schema.md` 中的 JSON Schema，并校验 DB / MQ / CACHE 细分字段和枚举同步。

后续需要：

1. 增强钉钉消息中的 DB / MQ / CACHE 细分展示。
2. 如果后续扩展完整项目、触发源、通知字段，再同步升级 schema 和代码对象。

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

已完成：

1. 对齐 `docs/04-risk-card-schema.md` 与后端 `RiskCard`。
2. 前端基于统一 schema 展示 DB / MQ / CACHE 细分风险项。
3. 补充 schema 校验测试，覆盖 DB / MQ / CACHE 细分字段。

后续任务：

1. 增强钉钉消息中的 DB / MQ / CACHE 细分展示。

验收标准：

- 风险卡片 JSON 有唯一权威结构。
- DB / MQ / CACHE 细分风险项能展示类型、置信度、命中原因、关联信号和证据。

### P5：DB 风险细粒度规则优化

目标：降低 Mapper XML、实体字段、migration 等 DB 相关变更的误报和误判，让风险卡片能解释“为什么命中”和“置信度有多高”。

已完成：

1. 更新 `docs/06-change-analysis-rules.md` 的 DB 细分规则设计。
2. 拆分 `DB` 为 `DB_SCHEMA`、`DB_SQL`、`ORM_MAPPING`、`ENTITY_MODEL`、`DATA_MIGRATION`。
3. 在风险项中增加 `confidence` / `reason` / `relatedSignals`。
4. 实现第一批 DB 细分识别规则。
5. 补充单元测试，覆盖 Mapper XML、entity 字段、migration、组合风险。

已满足：

- Mapper XML SQL 变更不再直接等同于 DB schema 风险。
- migration / DDL 变更能被高置信度识别为 DB schema 风险。
- 实体字段和 Mapper 映射组合变更能提示“疑似 DB schema 未同步”。
- 风险卡片能展示细分类型、命中原因和证据。

后续建议：

- 用真实 MR 样本继续校准命中条件，降低业务语义上的误报。
- 增强钉钉消息中的 DB / MQ / CACHE 细分展示。

### P6：API / CACHE / MQ / CONFIG 细粒度规则优化

目标：在 DB 细分闭环稳定后，逐步把其他粗粒度类型拆成可解释、可展示、可配置的细分规则，降低“只看到 MQ/CACHE/API/CONFIG 但不知道具体风险”的问题。

已完成：

1. 在 `docs/06-change-analysis-rules.md` 中补充 API 细分规划：
   - `API_ENDPOINT`
   - `API_REQUEST_SCHEMA`
   - `API_RESPONSE_SCHEMA`
   - `API_AUTH`
   - `API_ERROR_CONTRACT`
2. 实现 CACHE 第一轮细分：
   - `CACHE_KEY`
   - `CACHE_TTL`
   - `CACHE_INVALIDATION`
   - `CACHE_READ_WRITE`
   - `CACHE_SERIALIZATION`
3. 实现 MQ 第一轮细分：
   - `MQ_PRODUCER`
   - `MQ_CONSUMER`
   - `MQ_MESSAGE_SCHEMA`
   - `MQ_TOPIC_CONFIG`
   - `MQ_RETRY_DLQ`
4. 补充 CONFIG 细分规划：
   - `CONFIG_FEATURE_FLAG`
   - `CONFIG_DATASOURCE`
   - `CONFIG_MIDDLEWARE`
   - `CONFIG_SECURITY`
   - `CONFIG_ENVIRONMENT`
5. 新增 `V5__mq_cache_fine_grained_rule_templates.sql`，将 `backend-default` 模板升级到 MQ / CACHE 细分规则。
6. 补充单元测试覆盖 producer、consumer、message DTO、topic/group、cache TTL、cache evict、cache serialization。

建议实现顺序：

1. 第二轮做 `API`，重点解决接口路径、入参、出参、鉴权、错误码的兼容性表达。
2. 第三轮做 `CONFIG`，重点和 DB / MQ / CACHE / API 形成组合风险，而不是孤立地提示“配置变更”。
3. 对 MQ / CACHE 继续用真实 MR 样本校准误报和漏报。

第一轮 MQ / CACHE 已完成范围：

1. 保留 `MQ` / `CACHE` 聚合类型兼容旧模板。
2. 新增 `MQ_PRODUCER`、`MQ_CONSUMER`、`MQ_MESSAGE_SCHEMA`、`MQ_TOPIC_CONFIG`、`MQ_RETRY_DLQ`。
3. 新增 `CACHE_KEY`、`CACHE_TTL`、`CACHE_INVALIDATION`、`CACHE_READ_WRITE`、`CACHE_SERIALIZATION`。
4. 风险项继续使用 `confidence` / `reason` / `relatedSignals`。
5. 补单元测试覆盖 producer、consumer、message DTO、topic/group、cache key、TTL、evict、serialization。

验收标准：

- 只改 MQ listener 时，输出 `MQ_CONSUMER`，不直接泛化成所有 MQ 风险。
- 只改消息体 DTO 时，输出 `MQ_MESSAGE_SCHEMA`，并提示生产者/消费者兼容检查。
- 只改 topic/group 时，输出 `MQ_TOPIC_CONFIG`，并提示环境配置一致性。
- 只改缓存 key 拼接时，输出 `CACHE_KEY`，并提示新旧 key 兼容和清理策略。
- 只改 TTL 时，输出 `CACHE_TTL`，不直接断言缓存一致性问题。
- 修改 cache evict/delete 时，输出 `CACHE_INVALIDATION`，并提示脏数据风险。

## 6. 建议的下一轮 Codex 任务

建议按以下顺序继续推进：

1. `请新增 examples 目录下的 mock GitLab webhook、manual review 请求示例和 examples/README.md。`
2. `请清理 README，把大段 payload 抽离到 examples，并明确 mock webhook 和 manual review 两条验证路径。`
3. `请补一个 webhook 到 review result 的主链路集成测试，覆盖 mock payload 和 gitlab_api source。`
4. `请增强钉钉消息中的 DB / MQ / CACHE 细分展示。`
5. `请把 GitLab token 和钉钉 webhook 从环境变量升级为项目级数据库配置。`
6. `请在稳定性任务收口后，再实现 API 第一轮细分规则，保留 API 聚合类型兼容旧模板。`
7. `请在拿到 GitLab webhook 权限后，配置真实 webhook 并验证自动触发链路。`

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

