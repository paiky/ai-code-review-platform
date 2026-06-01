# 多端代码审查接入计划

> 状态说明：本文记录多端接入的总体设计。阶段 1（项目组前端管理）与阶段 2（端类型自动识别）已基本落地；阶段 3（多端 MR 拆分审查）仍为后续规划。分阶段 prompt 见 `docs/22-multi-target-next-phases-plan.md`。

## 1. 目标

平台从“以后端变更提醒为主”升级为“可识别端类型并按端选择规则提醒模板和 AI Review Profile”的审查平台。当前默认面向前后端分离仓库，一个 GitLab 项目归属一个端类型；混合仓库场景保留为后续多端拆分审查能力。

第一阶段目标：

- 现有后端项目行为保持不变。
- PC / APP 项目默认使用端侧 AI Review Profile。
- 后端维护类提醒卡片默认只对 `BACKEND` 启用。
- 任务列表、任务详情和设置页可以看到并配置项目组、端类型和端类型配置。

## 2. 端类型

内置端类型：

| targetType | 说明 | 默认规则模板 | 默认 AI Review Profile | 默认提醒卡片 |
| --- | --- | --- | --- | --- |
| `BACKEND` | 后端服务 | `backend-default` | `backend-default-ai-review` | 启用 |
| `WEB_PC` | PC Web / 管理端 / H5 | `frontend-default` | `web-pc-default-ai-review` | 关闭 |
| `APP_IOS` | iOS | `frontend-default` | `app-ios-default-ai-review` | 关闭 |
| `APP_ANDROID` | Android | `frontend-default` | `app-android-default-ai-review` | 关闭 |
| `APP_CROSS_PLATFORM` | Flutter / React Native / 小程序等 | `frontend-default` | `app-cross-platform-default-ai-review` | 关闭 |
| `GENERAL` | 无法明确归类 | `general-default` | `backend-default-ai-review` | 关闭 |

## 3. 数据模型

新增项目组：

- `project_groups`：项目组名称、描述、默认 Provider、状态。
- `projects.group_id`：项目归属项目组。
- `projects.supported_target_types`：项目可用端类型列表。

新增端类型配置：

- `project_target_configs.project_id`
- `project_target_configs.target_type`
- `project_target_configs.template_code`
- `project_target_configs.code_quality_profile_code`
- `project_target_configs.provider_code`
- `project_target_configs.path_patterns`
- `project_target_configs.reminder_card_enabled`
- `project_target_configs.enabled`

任务和结果补充：

- `review_tasks.target_type`
- `review_tasks.target_types_json`
- `review_tasks.code_quality_profile_code`
- `review_results.target_type`
- `review_results.reminder_card_enabled`

## 4. 解析规则

任务创建时按下面顺序确定端类型：

1. 手动审查请求显式传入 `targetType` 时优先使用。
2. 根据项目端类型配置中的 `pathPatterns` 匹配 changed files。
3. 多个端类型命中时，`targetTypes` 保存全部命中值，主 `targetType` 取第一个命中项。
4. 没有命中时使用项目默认 `BACKEND` 兼容旧行为。

规则模板和 AI Profile 选择：

- 优先使用手动请求中的 `templateCode` / `profileCode`。
- 否则使用 `project_target_configs` 中对应端类型配置。
- 再否则使用项目默认模板和默认 AI Review Profile。

## 5. 展示策略

- `BACKEND` 任务默认展示提醒卡片。
- PC / APP / GENERAL 任务如果 `reminderCardEnabled=false`，任务详情页隐藏“提醒卡片”Tab。
- 后端仍保存变更分析结果；关闭提醒卡片只影响风险卡片展示和规则提醒通知。
- 任务列表支持按项目组、项目和端类型过滤。

## 6. 验收

最小验收场景：

1. 老后端项目不做任何配置，仍能跑通 webhook/manual -> 分析 -> 提醒卡片 -> 通知 -> 落库。
2. 手动审查传 `targetType=WEB_PC`，任务使用 `web-pc-default-ai-review`，详情页不展示提醒卡片。
3. 配置项目 `WEB_PC` 路径为 `frontend/**`，未传 targetType 时能按路径匹配。
4. 任务列表能按项目组和端类型筛选。
