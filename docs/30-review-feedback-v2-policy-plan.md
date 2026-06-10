# Review 反馈学习 V2：项目规则候选与策略注入落地方案

## 状态

- 当前状态：方案已制定，尚未编码落地。
- 编写时间：2026-06-09
- 前置版本：`docs/29-review-feedback-v1-implementation.md`
- V2 目标：把 V1 中沉淀价值较高的反馈，人工转换为项目级 Review 策略，并在后续 AI Review 时作为项目上下文注入。

## 启动脚本说明

`scripts/run-backend.cmd` 与 `scripts/run-backend-python.ps1` 最终走同一个 Python 后端入口。

调用链：

```text
scripts/run-backend.cmd
  -> scripts/run-backend.ps1
  -> scripts/run-backend-python.ps1
```

区别：

- `run-backend.cmd` 是 Windows cmd 包装，负责设置 PowerShell 执行参数、转发参数、失败时提示。
- `run-backend-python.ps1` 是实际 Python 后端 runner，负责加载 `.local/gitlab.env`、设置 `PYTHONPATH`、选择 Python、执行 `dev/test/lint/migrate`。

因此，直接启动 `run-backend-python.ps1 dev` 与通过 `run-backend.cmd dev` 在后端行为上等价。项目默认推荐 `run-backend.cmd` 是为了团队统一入口；排查或你当前这种直接跑 Python 后端 runner 的方式也可以继续使用。

## V2 产品边界

V2 只做“人工确认后生效”的项目规则闭环：

```text
反馈池中的高价值反馈
  -> 管理员生成项目 Review 策略
  -> 策略可启用 / 停用 / 编辑
  -> 后续 AI Review 构造 prompt 时注入已启用策略
  -> rendered prompt 可预览注入内容
```

V2 不做：

- 不自动生成 Prompt patch。
- 不自动调整风险等级。
- 不做跨项目复用。
- 不做模型评测和效果回归。
- 不做 RAG 检索、向量库、知识库全文召回。
- 不让单条普通用户反馈自动影响后续 Review。

## V2 最小用户链路

1. 用户在任务详情中对某条规则提醒或 AI finding 提交反馈，并勾选“沉淀”。
2. 管理员进入“反馈池”，筛选 `suggestAsProjectRule=true` 或 `status=VALID` 的反馈。
3. 管理员点击“生成策略”。
4. 弹窗默认带出策略标题、策略内容、策略类型、适用风险类型。
5. 管理员确认后生成 `project_review_policies` 记录。
6. 管理员进入“项目 Review 策略”查看、编辑、启用或停用策略。
7. 后续对同一项目触发 AI Review 时，后端读取已启用策略并注入 prompt。
8. AI Review 结果仍正常落库，任务详情可通过 prompt 预览确认本次使用的项目规则。

## 数据库方案

### 新增表：`project_review_policies`

```sql
CREATE TABLE project_review_policies (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  policy_type VARCHAR(64) NOT NULL,
  risk_type VARCHAR(64) NULL,
  title VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  source_feedback_id BIGINT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  version INT NOT NULL DEFAULT 1,
  created_by VARCHAR(128) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_project_enabled (project_id, enabled),
  KEY idx_project_risk_type (project_id, risk_type),
  KEY idx_source_feedback (source_feedback_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 枚举

`policy_type`：

- `PROJECT_RULE`：项目级 Review 规则。
- `CONTEXT_FACT`：项目事实，例如统一鉴权、统一异常处理。
- `IGNORE_RULE`：忽略类策略，V2 可创建和展示，但不做强过滤。
- `RISK_LEVEL_POLICY`：等级策略，V2 可创建和展示，但不自动降级。

V2 实际注入 prompt 的类型：

- `PROJECT_RULE`
- `CONTEXT_FACT`

## 后端改动方案

### 新增模块

新增 `backend-python/app/project_review_policy/`：

- `models.py`
  - `ProjectReviewPolicy`
- `repository.py`
  - `ensure_project_review_policy_schema`
  - `create_policy_from_feedback`
  - `list_project_policies`
  - `update_policy`
  - `set_policy_enabled`
  - `list_enabled_policies_for_project`
- `service.py`
  - 反馈转策略的校验、默认标题和内容生成。
  - 策略列表、编辑、启停。
  - Prompt 注入文本生成。
- `api.py`
  - 策略管理接口。

### 数据迁移

新增：

```text
backend-python/migrations/bootstrap_sql/V35__project_review_policies.sql
```

### 反馈模块增强

调整 `backend-python/app/review_feedback/service.py`：

- 反馈状态为 `VALID` 或 `suggest_as_project_rule=true` 时，允许转换策略。
- 转换成功后，可把原反馈状态更新为 `CONVERTED`。

建议 V2 扩展 V1 status 枚举：

- `CONVERTED`

对应迁移不需要改表，仅后端枚举和前端展示增加状态。

### AI Review Prompt 注入

调整：

- `backend-python/app/code_quality/service.py`
- `backend-python/app/code_quality/prompt.py`

建议实现方式：

1. 在构造 Review request 时，根据 `project_id` 读取启用策略。
2. 增加 `projectReviewPolicies` 字段。
3. 在 prompt 拼装层追加一段固定结构：

```text
以下是当前项目已确认的 Review 策略。请结合这些策略判断风险，但不要因此忽略明显的安全、数据一致性或线上正确性问题。

1. [PROJECT_RULE][TRANSACTION] 本项目 Controller 层允许不写 try-catch
   本项目统一使用 GlobalExceptionHandler 处理 Controller 层异常，因此 Controller 方法中未显式 try-catch 不应直接判定为异常处理缺失风险。
```

安全约束：

- 单次最多注入 20 条。
- 单条 content 最多 1000 字符。
- 总注入文本最多 8000 字符。
- 仅注入同一 `project_id` 下 `enabled=true` 的策略。
- V2 不注入其它项目组策略。

### rendered prompt 预览

调整：

- `GET /api/code-quality-review-profiles/{profileCode}/rendered-prompt`

建议新增可选 query：

- `projectId`

有 `projectId` 时，预览中展示会注入的项目策略；无 `projectId` 时保持当前 profile 预览。

## 后端接口方案

### 1. 从反馈生成策略

```http
POST /api/risk-feedback/{feedbackId}/convert-to-policy
```

请求：

```json
{
  "policyType": "PROJECT_RULE",
  "riskType": "TRANSACTION",
  "title": "本项目统一由 GlobalExceptionHandler 处理 Controller 异常",
  "content": "Controller 方法未显式 try-catch 时，不应仅凭这一点判定异常处理缺失风险。",
  "enabled": true
}
```

响应：

```json
{
  "id": 1,
  "projectId": 1,
  "policyType": "PROJECT_RULE",
  "riskType": "TRANSACTION",
  "title": "...",
  "enabled": true,
  "sourceFeedbackId": 10
}
```

### 2. 查询项目策略

```http
GET /api/projects/{projectId}/review-policies
```

查询参数：

- `enabled`
- `policyType`
- `riskType`

### 3. 更新策略

```http
PUT /api/project-review-policies/{policyId}
```

请求字段：

- `policyType`
- `riskType`
- `title`
- `content`
- `enabled`

### 4. 启用 / 停用策略

```http
PUT /api/project-review-policies/{policyId}/enabled
```

请求：

```json
{
  "enabled": false
}
```

## 前端改动方案

### 反馈池页面增强

文件：

- `frontend/src/App.jsx`
- `frontend/src/styles.css`

在现有“反馈池”列表增加：

- 筛选：`建议沉淀`
- 操作：`生成策略`
- 状态展示：`已沉淀`

生成策略弹窗：

- 策略类型
- 适用风险类型
- 策略标题
- 策略内容
- 是否启用

默认值：

- `policyType` 默认 `PROJECT_RULE`
- `riskType` 取反馈的 `riskType`
- `title` 取反馈风险标题，前缀可改为“关于 xxx 的项目规则”
- `content` 由反馈原因和补充说明拼出，管理员可编辑

### 项目 Review 策略页面

V2 最小做法：

- 在顶部导航新增“Review 策略”，或在“反馈池”页面内增加项目策略抽屉 / tab。

推荐最小实现：

- 先在“反馈池”页面增加一个 `项目策略` tab，避免导航继续膨胀。

字段：

- 项目
- 策略类型
- 风险类型
- 标题
- 内容摘要
- 来源反馈
- 启用状态
- 版本
- 更新时间
- 操作：编辑、启用、停用

## 测试方案

### 后端契约测试

新增：

```text
backend-python/tests/contract/test_project_review_policy_api_contract.py
```

覆盖：

- 从反馈生成策略。
- 只允许任务所属项目生成策略。
- 查询项目策略。
- 编辑策略。
- 启用 / 停用策略。
- 已启用策略被读取到 AI Review request。
- rendered prompt 带 `projectId` 时包含项目策略。

### 单元测试

新增：

```text
backend-python/tests/unit/test_project_review_policy_prompt.py
```

覆盖：

- 策略注入文本排序。
- 条数限制。
- 单条内容截断。
- 总长度限制。
- `IGNORE_RULE` / `RISK_LEVEL_POLICY` V2 不注入。

### 前端验证

```powershell
.\scripts\run-frontend.cmd build
```

后端最小验证：

```powershell
.\scripts\run-backend.cmd test tests\contract\test_project_review_policy_api_contract.py tests\unit\test_project_review_policy_prompt.py
```

直接用 Python runner 也等价：

```powershell
.\scripts\run-backend-python.ps1 test tests\contract\test_project_review_policy_api_contract.py tests\unit\test_project_review_policy_prompt.py
```

## 验收标准

V2 完成后必须满足：

1. 管理员可以从反馈池把一条反馈转换为项目策略。
2. 项目策略能在前端查看、编辑、启用、停用。
3. 后端只会把同项目、已启用、V2 允许类型的策略注入 AI Review prompt。
4. rendered prompt 可以预览项目策略注入结果。
5. 停用策略后，后续 Review prompt 不再包含该策略。
6. V2 不改变规则提醒卡片生成逻辑，不直接影响规则引擎。
7. V2 不自动改全局 Prompt 或模型配置。

## 风险与处理

### Prompt 污染

风险：项目策略写得过宽，导致模型漏报真实问题。

处理：

- Prompt 中明确策略不能覆盖安全、数据一致性、线上正确性硬风险。
- V2 只允许人工确认后启用。
- 每条策略可停用。

### 策略过多导致 Prompt 变长

处理：

- 限制单次注入数量、单条长度、总长度。
- 后续 V3 再做按风险类型和路径检索。

### 反馈原因质量不足

处理：

- V2 不自动生成策略。
- 弹窗只预填草稿，必须管理员确认。
- `status=INSUFFICIENT` 的反馈默认不展示生成策略入口。

### 项目隔离

处理：

- 所有策略按 `project_id` 隔离。
- V2 不做项目组共享和平台级规则复用。

## 分阶段落地 Prompt

### 总控 Prompt

```text
请阅读 AGENTS.md、README.md、docs/29-review-feedback-v1-implementation.md、docs/30-review-feedback-v2-policy-plan.md，以及当前 backend-python/app/review_feedback、backend-python/app/code_quality、frontend/src/App.jsx 相关代码。

接下来按 docs/30 的 V2 方案分阶段落地。每次只推进一个阶段。允许自主修改 backend-python、frontend、docs、examples、tests 中与本阶段直接相关的文件；不要修改 legacy Java backend；不要实现 V2 范围外的自动 Prompt 改写、模型评测、RAG、跨项目复用。

每个阶段完成后必须停止，输出“改了什么、为什么、如何验证”，等待用户验证并明确回复“继续下一阶段”后再推进。
```

### 阶段 1 Prompt：数据结构与后端策略 API

```text
请只落地 V2 阶段 1：新增 project_review_policies 表、后端模型、repository、service、API，以及从 risk feedback 转换为 policy 的接口。

范围：
- backend-python/app/project_review_policy/*
- backend-python/app/review_feedback/service.py 和 api.py 中必要的 convert-to-policy 接口
- backend-python/app/main.py router 注册
- backend-python/migrations/bootstrap_sql/V35__project_review_policies.sql
- backend-python/tests/contract/test_project_review_policy_api_contract.py
- docs/30 阶段 1 验证记录

不要做 prompt 注入，不要改前端。完成后停止，等待用户验证。
```

### 阶段 2 Prompt：前端反馈池生成策略与策略管理

```text
请只落地 V2 阶段 2：前端反馈池增加“生成策略”操作，并增加项目策略管理视图。

范围：
- frontend/src/App.jsx
- frontend/src/styles.css
- docs/30 阶段 2 验证记录

要求：
- 从反馈池可打开生成策略弹窗。
- 可查询、编辑、启用、停用项目策略。
- 不做 prompt 注入。

完成后运行前端 build，停止等待用户验证。
```

### 阶段 3 Prompt：AI Review Prompt 注入与预览

```text
请只落地 V2 阶段 3：AI Review 执行时读取同项目已启用 project_review_policies，并注入 prompt；rendered prompt 支持 projectId 预览。

范围：
- backend-python/app/project_review_policy/service.py
- backend-python/app/code_quality/service.py
- backend-python/app/code_quality/prompt.py
- backend-python/app/code_quality/api.py 如需 query 参数
- backend-python/tests/unit/test_project_review_policy_prompt.py
- backend-python/tests/contract/test_code_quality_api_contract.py 中新增或调整与 rendered prompt 相关的最小测试
- docs/30 阶段 3 验证记录

要求：
- 仅注入 PROJECT_RULE / CONTEXT_FACT。
- 同项目隔离。
- 有数量和长度限制。
- 不实现 RAG、评测集、自动降权。

完成后停止等待用户验证。
```

### 阶段 4 Prompt：文档与示例收口

```text
请只落地 V2 阶段 4：补充 README / API 契约 / 示例验证步骤。

范围：
- README.md
- docs/03-api-contract.md
- docs/30-review-feedback-v2-policy-plan.md
- examples/ 如需新增最小请求示例

要求：
- 写清如何从反馈生成项目策略。
- 写清如何验证策略注入 rendered prompt。
- 记录本地已知测试结果。

完成后停止，等待用户最终验收。
```

## Agent 授权边界

Agent 可自主推进：

- 新增 Python 后端 V2 策略模块。
- 新增 MySQL bootstrap SQL。
- 新增和调整 V2 相关 API。
- 新增契约 / 单元测试。
- 新增前端反馈池和策略管理的最小交互。
- 更新 V2 文档、API 契约和 README。

Agent 不可自主推进：

- 不修改 Java legacy backend。
- 不做自动 Prompt 改写。
- 不做模型微调。
- 不接向量库或复杂 RAG。
- 不改变 V1 feedback 表已落库数据语义。
- 不把项目策略跨项目组共享。
- 不默认启用任何由系统自动生成且未人工确认的策略。

## 每阶段停止规则

每个阶段完成后必须停止，并等待用户完成本地验证。只有用户明确回复“继续下一阶段”后，才进入下一阶段。
