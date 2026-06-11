# AI Review 平台：风险反馈学习中心落地方向文档

## 一、功能定位

当前平台已有 AI Review 风险识别、风险卡片展示、Review Task 查询等基础能力。下一阶段不直接追求“自动训练模型”或“自动修改 Prompt”，而是先建设一个可持续演进的 **风险反馈学习中心**。

该能力的目标是：

1. 允许用户对 AI 生成的风险点进行反馈。
2. 记录哪些风险点是有效的、误判的、等级过高的、重复的。
3. 将用户反馈沉淀为项目维度的 Review 经验。
4. 后续逐步支持项目规则、项目知识、模型效果评估和 Prompt/策略版本管理。
5. 让 AI Review 结果逐渐贴合不同项目组的开发规范和代码习惯。

本阶段不要直接做自动改 Prompt、模型微调、复杂评测平台。当前优先目标是先打通“风险卡片 → 用户反馈 → 反馈记录 → 反馈池 → 项目规则候选”的闭环。

------

## 二、整体产品方向

最终形态可以叫：

**Review 反馈学习中心**

包含以下模块：

1. 风险卡片反馈
2. Review 反馈池
3. 项目规则候选
4. 项目 Review 策略
5. 反馈统计报表
6. 后续扩展：Prompt 版本、模型效果对比、评测样本库

当前阶段只实现前 3 个模块，并为后续扩展预留数据结构。

------

## 三、用户操作链路

### 1. 开发者在风险卡片上反馈

在 Review Task 详情页，每条风险卡片底部增加反馈操作：

- 有用
- 误判
- 风险等级过高
- 重复提醒
- 已修复

点击“误判”或“风险等级过高”时，弹出反馈窗口。

反馈窗口字段：

- 反馈类型
- 误判原因
- 补充说明
- 是否建议沉淀为项目规则

误判原因建议包含：

- 当前项目允许这种写法
- 已有外部逻辑兜底
- AI 缺少上下文
- 规则不适用于本项目
- 风险等级过高
- 风险描述不准确
- 重复提醒
- 其他

### 2. 平台记录反馈

每一次用户反馈都要保存，不能只更新风险卡片状态。

反馈记录需要关联：

- projectId
- reviewTaskId
- riskCardId
- mrId
- riskType
- riskTitle
- feedbackType
- reasonType
- reasonText
- userId
- status
- createdAt
- updatedAt

### 3. 管理员查看反馈池

新增一个“Review 反馈池”页面，用于项目负责人或平台管理员查看所有反馈。

列表字段：

- 项目
- Review Task
- MR
- 风险类型
- 风险标题
- 原始风险等级
- 用户反馈类型
- 反馈原因
- 补充说明
- 反馈人
- 状态
- 创建时间
- 操作

支持筛选：

- 项目
- 风险类型
- 反馈类型
- 状态
- 时间范围

状态建议：

- 待分析
- 信息不足
- 有效反馈
- 已沉淀
- 已忽略

### 4. 管理员将高价值反馈沉淀为项目规则候选

在反馈池中，管理员可以对一条反馈执行操作：

- 标记为有效反馈
- 标记为信息不足
- 忽略
- 生成项目规则候选

项目规则候选用于记录某个项目的特殊规范、约定、例外情况。

例如：

规则标题：

> 本项目 Controller 层允许不写 try-catch

规则内容：

> 本项目统一使用 GlobalExceptionHandler 处理 Controller 层异常，因此 Controller 方法中未显式 try-catch 不应直接判定为异常处理缺失风险。

后续 AI Review 可以将这些项目规则作为上下文提供给模型。

------

## 四、阶段划分

### V1：风险反馈记录闭环

目标：先让用户能反馈，平台能记录，管理员能查看。

范围：

1. 风险卡片增加反馈按钮。
2. 支持提交反馈。
3. 新增 risk_feedback 表。
4. 新增反馈查询接口。
5. 新增反馈池页面。
6. 支持反馈状态流转：待分析、有效反馈、信息不足、已忽略。

V1 不做：

- 自动改 Prompt
- 自动影响后续 Review
- 模型评测
- 知识库检索
- 自动生成规则

### V2：项目规则候选

目标：让高质量反馈可以被沉淀为项目经验。

范围：

1. 新增 project_review_policy 表。
2. 在反馈池中支持“生成项目规则候选”。
3. 项目规则有启用/停用状态。
4. Review 时可以读取当前项目已启用规则。
5. 将项目规则拼接到 AI Review 上下文中。

V2 可以先用简单拼接方式，不需要复杂 RAG。

### V3：反馈分析和策略优化

目标：提升平台持续改进能力。

范围：

1. AI 自动分析反馈理由质量。
2. 统计不同项目、不同风险类型的误判率。
3. 识别高频误判风险。
4. 支持风险等级降权建议。
5. 支持 Prompt/规则版本记录。
6. 逐步建设 Review Eval Case，用于评估改进前后效果。

------

## 五、建议数据表

### 1. risk_feedback

用于记录每次风险反馈。

字段建议：

- id
- project_id
- review_task_id
- mr_id
- risk_card_id
- risk_type
- risk_title
- original_risk_level
- feedback_type
- reason_type
- reason_text
- suggest_as_project_rule
- user_id
- user_name
- status
- admin_comment
- created_at
- updated_at

feedback_type 可选值：

- USEFUL
- FALSE_POSITIVE
- LEVEL_TOO_HIGH
- DUPLICATE
- FIXED

reason_type 可选值：

- PROJECT_ALLOWED
- HAS_EXTERNAL_GUARD
- CONTEXT_MISSING
- RULE_NOT_APPLICABLE
- LEVEL_TOO_HIGH
- DESCRIPTION_INACCURATE
- DUPLICATE
- OTHER

status 可选值：

- PENDING
- VALID
- INSUFFICIENT
- IGNORED
- CONVERTED

### 2. project_review_policy

用于记录项目级 Review 规则。

字段建议：

- id
- project_id
- policy_type
- risk_type
- title
- content
- source_feedback_id
- enabled
- version
- created_by
- created_at
- updated_at

policy_type 可选值：

- PROJECT_RULE
- IGNORE_RULE
- RISK_LEVEL_POLICY
- PROMPT_PATCH
- CONTEXT_FACT

当前阶段主要使用 PROJECT_RULE 和 CONTEXT_FACT。

------

## 六、后端接口建议

### 1. 提交风险反馈

POST /api/review-tasks/{taskId}/risk-cards/{riskCardId}/feedback

请求体：

- feedbackType
- reasonType
- reasonText
- suggestAsProjectRule

返回：

- feedbackId
- status

### 2. 查询反馈池

GET /api/risk-feedback

查询参数：

- projectId
- riskType
- feedbackType
- status
- startTime
- endTime
- page
- size

### 3. 更新反馈状态

PUT /api/risk-feedback/{feedbackId}/status

请求体：

- status
- adminComment

### 4. 生成项目规则候选

POST /api/risk-feedback/{feedbackId}/convert-to-policy

请求体：

- title
- content
- policyType
- riskType
- enabled

### 5. 查询项目规则

GET /api/projects/{projectId}/review-policies

### 6. 启用/停用项目规则

PUT /api/project-review-policies/{policyId}/enabled

------

## 七、前端页面建议

### 1. Review Task 详情页

在原有风险卡片中增加反馈区。

风险卡片展示结构：

- 风险标题
- 风险等级
- 风险类型
- 问题描述
- 影响范围
- 建议修改
- 代码位置
- 反馈操作区

反馈操作区：

- 有用
- 误判
- 等级过高
- 重复
- 已修复

如果已反馈，展示：

- 当前反馈状态
- 反馈类型
- 反馈原因
- 反馈时间

### 2. Review 反馈池页面

页面用于集中管理反馈。

顶部统计卡片：

- 总反馈数
- 误判数
- 等级过高数
- 重复提醒数
- 已沉淀规则数

列表操作：

- 查看原始风险
- 标记有效
- 标记信息不足
- 忽略
- 生成项目规则

### 3. 项目 Review 策略页面

展示当前项目下已沉淀的规则。

字段：

- 规则标题
- 规则类型
- 适用风险类型
- 规则内容
- 来源反馈
- 状态
- 版本
- 创建时间
- 操作

操作：

- 启用
- 停用
- 编辑
- 删除

------

## 八、Review 执行时如何使用项目规则

V2 阶段可以采用简单方式：

1. Review Task 创建时，根据 projectId 查询已启用的 project_review_policy。
2. 将这些规则加入 AI Review 的上下文。
3. 明确告诉模型：这些是当前项目的 Review 约定，需要结合判断。
4. 模型输出风险时，如果某条项目规则适用，应避免重复报告或降低风险等级。

示例上下文：

```text
以下是当前项目的 Review 规则，请在判断风险时结合使用：

1. 本项目 Controller 层允许不写 try-catch，因为统一由 GlobalExceptionHandler 处理。
2. 本项目 Redis key 统一由 CacheKeyBuilder 生成，调用处无需重复校验 key 格式。
3. 本项目内部接口由网关统一鉴权，业务方法未出现鉴权代码时，不应直接判定为权限风险。
```

------

## 九、实现原则

1. 先记录反馈，再谈自动学习。
2. 先项目隔离，再考虑平台级复用。
3. 先人工确认，再自动生效。
4. 先结构化反馈，再分析自由文本。
5. 先规则和知识库增强，不要一开始改全局 Prompt。
6. 所有策略都要有来源，能追溯到具体反馈。
7. 所有规则都要支持启用、停用、版本记录。
8. 不同项目组的规则不能默认互相影响。
9. 模型差异不要通过全局 Prompt 直接修正，后续应支持模型适配层。
10. 当前阶段不做模型微调。

------

## 十、当前 agent 任务建议

请 agent 先完成以下工作：

1. 阅读当前项目结构，确认 Review Task、Risk Card、Rule Engine、前端页面所在模块。
2. 梳理当前风险卡片的数据结构。
3. 判断是否已有 risk_card 独立表；如果没有，确认 riskCardId 如何生成和定位。
4. 给出 V1 的最小改动方案。
5. 先实现 risk_feedback 表和反馈提交接口。
6. 再实现反馈池页面。
7. 最后实现从反馈池生成 project_review_policy 的 V2 能力。

不要让 agent 一次性实现完整“反馈学习中心”，而是先实现 V1，再逐步进入 V2/V3。