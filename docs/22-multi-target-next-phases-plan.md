# 多端接入后续三阶段落地计划

> 状态说明：本文是多端能力的阶段推进文档。阶段 1 / 阶段 2 的项目组管理、项目端类型配置、自动识别依据展示和单仓单端配置能力已部分落地；当前产品默认一个 GitLab 项目归属一个端类型。阶段 3 的“多端 MR 拆分审查”仍是后续规划。

## 1. 执行结论

当前多端能力已经完成第一版基础：

- 项目组后端 API 可用。
- 项目端类型配置可用。
- 任务可记录 `targetType` / `targetTypes`。
- PC / APP 默认可切换到对应 AI Review Profile。
- 非后端端类型可隐藏后端维护类提醒卡片。

下一步不建议直接做权限体系或复杂配置继承。建议按三个小阶段推进：

1. 项目组前端管理与项目绑定。当前已基本落地，后续按使用反馈微调。
2. 自动端类型识别增强。当前已支持识别依据展示和单端回填，后续继续补充样本和规则。
3. 多端 MR 拆分审查。仍为后续规划。

每个阶段完成后必须停止，等待用户验证并确认“继续下一阶段”后再推进。

## 2. 阶段 1：项目组前端管理与项目绑定

### 2.1 目标

让项目组从“后端 API 可用”变成“前端可管理、可筛选、可绑定”的完整闭环。

当前项目组主要只能通过接口创建和绑定，前端仍不够顺手。阶段 1 只解决项目组管理，不做权限、不做配置继承。

### 2.2 范围

前端：

- 在“设置”页新增项目组管理区域。
- 支持创建项目组。
- 支持编辑项目组名称、编码、描述、默认 Provider。
- 支持停用项目组。
- 支持把项目绑定到项目组。
- 项目列表按项目组筛选或分组展示。
- 任务列表保留并优化项目组筛选。

后端：

- 补齐项目组 API 的必要校验。
- `groupCode` 不允许重复。
- 默认项目组不允许停用或删除。
- 项目绑定不存在项目组时返回清晰错误。
- 如果需要，补 `GET /api/project-groups/{groupId}`。

文档：

- 更新 README 的项目组使用说明。
- 更新 `docs/18-project-integration-user-guide.md`，说明项目组只用于归类和筛选，不代表权限。

### 2.3 不做什么

- 不做用户、角色、权限。
- 不做项目组级配置继承。
- 不做项目组级钉钉默认 webhook 继承。
- 不做跨项目统计看板。

### 2.4 验收

- 可以在前端新增“移动业务组”。
- 可以把已有项目绑定到“移动业务组”。
- 任务列表按“移动业务组”筛选后，只展示该组项目的任务。
- 默认项目组仍存在，未绑定项目默认归入默认项目组。
- 后端 contract 测试覆盖项目组创建、更新、绑定和重复 `groupCode`。
- 前端 build 通过。

## 3. 阶段 2：自动端类型识别增强

### 3.1 目标

减少 PC / iOS / Android 项目接入后的手工配置成本。新 GitLab 项目首次 webhook 进入平台时，能基于仓库路径、仓库名或 namespace 给出更合理的端类型默认配置。

当前新项目默认是 `BACKEND`。如果 PC 端或 iOS 端是独立仓库，需要手动把项目改成 `WEB_PC` 或 `APP_IOS`。阶段 2 解决这个问题。

### 3.2 范围

后端识别规则：

- 基于 changed files 路径推断端类型：
  - `ios/**`、`**/*.swift`、`Podfile` -> `APP_IOS`
  - `android/**`、`**/*.kt`、`build.gradle`、`settings.gradle` -> `APP_ANDROID`
  - `frontend/**`、`web/**`、`src/**/*.tsx`、`src/**/*.jsx`、`package.json` -> `WEB_PC`
  - `flutter/**`、`**/*.dart`、`pubspec.yaml`、`rn/**`、`miniapp/**` -> `APP_CROSS_PLATFORM`
  - `src/main/java/**`、`src/main/resources/**`、`pom.xml`、`backend-python/**` -> `BACKEND`
- 基于 GitLab project name / path_with_namespace 辅助推断：
  - 包含 `ios`、`iphone` 可建议 `APP_IOS`
  - 包含 `android` 可建议 `APP_ANDROID`
  - 包含 `web`、`frontend`、`h5`、`pc` 可建议 `WEB_PC`
  - 包含 `server`、`service`、`backend`、`api` 可建议 `BACKEND`
- 首次自动创建项目时：
  - 保存 `detectedTargetTypes` 或等价信息到项目配置响应中。
  - 如果只命中一个端类型，可自动创建该端类型配置，并把项目主默认端类型视为该端。
  - 如果命中多个端类型，保留多个 `project_target_configs`，但任务仍按当前主 `targetType` 逻辑执行。

前端展示：

- 项目端类型配置区域展示“自动识别依据”。
- 如果项目仍是默认 `BACKEND`，但最近变更明显是 iOS / Android / Web，展示一个提示。
- 提供手动保存“当前项目所属端类型”的操作，必要时可根据识别依据快速回填。

文档：

- README 增加“单端仓库推荐使用 `**/*`”说明。
- 用户手册增加“首次接入后检查端类型识别结果”说明。

### 3.3 不做什么

- 不做机器学习或 LLM 推断。
- 不做扫描整个 GitLab 仓库树，只使用 webhook / compare / diff 中已有 changed files。
- 不在识别不明确时强行覆盖用户已有配置。
- 不做多端子任务拆分，这属于阶段 3。

### 3.4 验收

- 新 iOS 仓库首次 webhook 中只有 `ios/AppDelegate.swift` 时，项目自动出现 `APP_IOS` 配置。
- 新 Web 仓库首次 webhook 中只有 `src/pages/Home.tsx` 和 `package.json` 时，项目自动出现 `WEB_PC` 配置。
- 旧后端项目已有配置不被自动覆盖。
- 多端仓库同时出现 `server/**` 和 `web/**` 时，项目记录多个端类型配置。
- contract 测试覆盖路径识别、仓库名识别、不覆盖已有配置。
- 前端 build 通过。

## 4. 阶段 3：多端 MR 拆分审查

### 4.1 目标

一个 MR 同时修改多个端时，不再只用一个主 `targetType` 审全部 diff，而是按端类型拆分审查结果。

目标链路：

```text
一次 GitLab webhook
  -> 一个父任务
  -> 多个端类型审查单元
      BACKEND: 规则提醒卡片 + 后端 AI Review
      WEB_PC: Web AI Review
      APP_IOS: iOS AI Review
      APP_ANDROID: Android AI Review
```

### 4.2 推荐数据模型

新增审查单元表：

```text
review_task_target_results
```

建议字段：

- `id`
- `task_id`
- `project_id`
- `target_type`
- `template_code`
- `code_quality_profile_code`
- `provider_code`
- `changed_files_json`
- `change_analysis_json`
- `risk_card_json`
- `reminder_card_enabled`
- `code_quality_result_id`
- `status`
- `risk_level`
- `created_at`
- `updated_at`

兼容策略：

- `review_tasks.targetType` 保留为主端类型，用于列表兼容展示。
- `review_tasks.targetTypes` 保存所有命中端类型。
- 老 `review_results` 保持作为主结果；第一版可继续写主端结果，新增表保存多端结果。
- 前端详情页新增“端类型审查”视图，逐个端展示。

### 4.3 处理流程

1. webhook / manual 入口先解析 changed files。
2. 按 `project_target_configs.pathPatterns` 将 changed files 分桶。
3. 每个命中的端类型生成一个审查单元。
4. `BACKEND` 单元生成规则提醒卡片。
5. 非后端单元默认不生成后端维护类提醒卡片，只做端侧 AI Review。
6. AI Review 按审查单元分别使用对应 Profile 和 Provider。
7. 通知策略第一版保持克制：
   - 如果有后端提醒卡片，继续发送规则提醒或合并 AI Review 通知。
   - 多端 AI Review 通知可先汇总到一条消息，避免群消息爆炸。

### 4.4 前端展示

任务详情页：

- 增加“端类型审查”Tab。
- 每个端类型一个折叠面板。
- 面板展示：
  - 端类型
  - changed files 数量
  - 使用的模板/Profile/Provider
  - 提醒卡片状态
  - AI Review 状态、问题数、摘要

任务列表：

- `targetTypes` 多个时展示多个 Tag。
- 风险等级取各端最高等级。
- 提醒项数量取启用提醒卡片端的总数。

### 4.5 不做什么

- 不把一个 GitLab webhook 拆成多条独立顶层任务。
- 不改变 GitLab webhook URL。
- 不要求钉钉按每个端类型单独推送。
- 不做跨端依赖图谱或发布编排。

### 4.6 验收

- 一个 MR 同时修改 `server/**` 和 `web/**` 时，任务详情能看到 `BACKEND` 和 `WEB_PC` 两个审查单元。
- `BACKEND` 单元使用 `backend-default-ai-review`，并显示提醒卡片。
- `WEB_PC` 单元使用 `web-pc-default-ai-review`，默认隐藏提醒卡片。
- 单端 MR 行为与当前版本兼容。
- contract 测试覆盖多端分桶、单端兼容、前端结果 API。
- 前端 build 通过。

## 5. 分阶段落地 Prompt

### 5.1 阶段 1 Prompt：项目组前端管理

```text
请按 docs/22-multi-target-next-phases-plan.md 推进阶段 1，只做项目组前端管理与项目绑定。

要求：
1. 先阅读 AGENTS.md、README.md、docs/10-local-dev-pitfalls.md、docs/21-multi-target-review-plan.md、docs/22-multi-target-next-phases-plan.md。
2. 只实现项目组管理闭环，不做权限、不做配置继承、不做多端拆分审查。
3. 前端在“设置”页增加项目组管理区域，支持新增、编辑、停用项目组，以及项目绑定项目组。
4. 后端补必要校验：groupCode 唯一、默认项目组不可停用、绑定不存在项目组时返回清晰错误。
5. 更新 README 和 docs/18-project-integration-user-guide.md 的项目组使用说明。
6. 补 contract 测试，覆盖项目组创建、更新、重复 groupCode、项目绑定。
7. 跑最小验证：相关后端 contract 测试 + 前端 build。

完成后必须停止，汇报改了什么、为什么、如何验证、剩余风险，并等待用户确认“继续阶段 2”。
```

### 5.2 阶段 2 Prompt：自动端类型识别增强

```text
请按 docs/22-multi-target-next-phases-plan.md 推进阶段 2，只做自动端类型识别增强。

要求：
1. 先阅读 AGENTS.md、README.md、docs/10-local-dev-pitfalls.md、docs/21-multi-target-review-plan.md、docs/22-multi-target-next-phases-plan.md。
2. 只基于 webhook / compare / diff 中已有 changed files、项目名、namespace 做规则推断，不扫描整个 GitLab 仓库。
3. 新项目首次 webhook 时，根据路径或项目名自动建议或创建端类型配置。
4. 不覆盖用户已有端类型配置。
5. 前端展示端类型自动识别依据，并支持手动保存当前项目所属端类型。
6. 更新 README 和项目接入手册，说明单端仓库可用 `**/*`。
7. 补 contract 测试，覆盖 iOS、Android、Web、Backend、多端混合和“不覆盖已有配置”。
8. 跑最小验证：相关后端 contract 测试 + 前端 build。

完成后必须停止，汇报改了什么、为什么、如何验证、剩余风险，并等待用户确认“继续阶段 3”。
```

### 5.3 阶段 3 Prompt：多端 MR 拆分审查

```text
请按 docs/22-multi-target-next-phases-plan.md 推进阶段 3，只做多端 MR 拆分审查。

要求：
1. 先阅读 AGENTS.md、README.md、docs/10-local-dev-pitfalls.md、docs/21-multi-target-review-plan.md、docs/22-multi-target-next-phases-plan.md。
2. 一个 GitLab webhook 仍创建一个顶层 review task，不拆成多条顶层任务。
3. 新增审查单元模型/表，用于保存每个 targetType 的 changed files、分析结果、提醒卡片状态和 AI Review 关联结果。
4. 按 project_target_configs.pathPatterns 将 changed files 分桶。
5. BACKEND 单元保留规则提醒卡片；PC / APP 单元默认只做 AI Review。
6. 前端任务详情新增“端类型审查”Tab，按端类型展示各自状态和结果。
7. 钉钉第一版只做汇总通知，不按每个端类型单独轰炸。
8. 保持单端任务旧行为兼容。
9. 补 contract 测试，覆盖多端分桶、单端兼容、端类型结果 API。
10. 跑最小验证：相关后端 contract 测试 + 前端 build。

完成后必须停止，汇报改了什么、为什么、如何验证、剩余风险，并等待用户验收。
```

## 6. 总控 Prompt

```text
请阅读 AGENTS.md、README.md、docs/10-local-dev-pitfalls.md、docs/21-multi-target-review-plan.md、docs/22-multi-target-next-phases-plan.md，然后按文档中的阶段顺序推进多端接入后续能力。

授权范围：
1. 可以修改 backend-python/、frontend/、docs/、examples/ 中与当前阶段直接相关的文件。
2. 可以补充 migration、contract 测试和前端构建验证。
3. 可以运行本地非破坏性验证命令。

硬性边界：
1. 每次只推进一个阶段。
2. 阶段 1 未完成并经用户确认前，不进入阶段 2。
3. 阶段 2 未完成并经用户确认前，不进入阶段 3。
4. 不做权限体系。
5. 不改 GitLab webhook URL。
6. 不把一个 webhook 拆成多条顶层任务。
7. 不把 API Key、GitLab token、DingTalk webhook 写入代码、日志、测试快照或文档。
8. 每个阶段完成后必须停止，等待用户确认“继续下一阶段”。

先从阶段 1：项目组前端管理与项目绑定开始。
```
