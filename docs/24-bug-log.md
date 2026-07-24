# BUG 记录

> 状态说明：本文记录真实使用中发现的 BUG 与修复状态，供回归对照。新 BUG 继续在本文件追加；当前实现与验证步骤以 `README.md` 为准。

本文从 2026-05-27 开始记录用户在真实使用中发现的 BUG、影响、根因和修复状态。每条记录都应包含可复现线索，便于后续回归验证。

## BUG-20260527-001 非默认项目组未配置钉钉机器人时误推送到默认项目组

状态：已修复

发现时间：2026-05-27

现象：

- 最新任务 `351` 属于 `IOS端` 项目组，项目为 `here/here-ios`，端类型为 `APP_IOS`。
- `IOS端` 项目组没有配置钉钉机器人。
- 任务仍推送到了 `默认通用项目组` 下配置的钉钉机器人。

期望：

- 默认项目组也是普通项目组，只服务归属默认项目组的项目。
- 非默认项目组没有启用钉钉机器人时，通知记录应为 `SKIPPED`。
- 不应回退发送到默认项目组或其它项目组机器人。

根因：

- `enabled_webhooks_for_task()` 在任务所属项目组没有启用机器人时，会主动回退查询默认项目组机器人。
- `_resolve_skipped_result()` 通过该回退逻辑判断存在可用机器人，因此允许继续发送。

修复：

- 任务通知只查询任务所属项目组的启用机器人。
- 任务所属项目组无机器人时直接返回 `DINGTALK_WEBHOOKS_EMPTY` / `SKIPPED`。
- 更新回归测试，确保空项目组不会调用默认项目组机器人。

回归验证：

- 运行 `backend-python/tests/contract/test_gitlab_dingtalk_integration.py::test_dingtalk_delivery_skips_when_project_group_has_no_webhooks`。

## BUG-20260718-001 Agent Review 设置页因未定义处理函数崩溃

状态：已修复

发现时间：2026-07-18

现象：

- 打开设置页后，浏览器控制台报 `ReferenceError: testAgentSettings is not defined`。
- `TemplateConfig` 渲染失败，整个设置页面无法使用。

根因：

- Agent Review 设置卡片引用了 `testAgentSettings`，但没有实现该函数，React 在渲染 `onClick` 属性时立即抛错。
- `saveAgentSettings` 同样未实现，只因位于箭头函数体内而没有在首屏渲染时立即报错。
- 前端将配置测试成功状态误写为 `READY`，与后端 `QUEUED / RUNNING / SUCCESS / FAILED` 契约不一致。
- Agent 设置卡片虽然加入了 `collapseItems`，但没有加入最终的 `orderedCollapseItems` 白名单；即使修复运行时错误，卡片仍不会显示。

修复：

- 实现 Agent 设置保存、保留原 Key、替换 Key 和清除 Key。
- 实现 Worker 配置测试提交及两秒间隔的状态轮询，并支持页面重新打开后恢复轮询。
- 按后端状态展示排队、运行、成功、失败和轮询超时；成功状态统一为 `SUCCESS`。
- Worker 离线或设置尚未保存时，在前端给出明确提示。
- 将 `agent-review-settings` 加入设置页最终渲染顺序。

回归验证：

- 运行 `scripts/run-frontend.cmd build`。
- 打开 `/settings`，确认页面正常渲染；分别验证保存、清除 Key、Worker 离线提示和配置测试状态流转。

## BUG-20260724-001 项目组 Agent Review 引擎选择未保存

状态：已修复

发现时间：2026-07-24

现象：

- 设置页已经提供项目组 `STANDARD / AGENT` 选择和 Agent 源码外发授权，但入口位于“AI Review 配置”，用户容易在“项目组 / 端类型配置”中找不到。
- 即使在“AI Review 配置”完成选择并保存，刷新后仍恢复原值。

根因：

- “保存项目组 AI Review 策略”的请求体遗漏 `reviewEngine` 和 `agentSourceExportAllowed`，界面状态没有持久化到后端。
- Agent 全局配置卡没有说明“启用能力”与“切换项目组主引擎”是两个独立步骤。

修复：

- 保存项目组策略时一并提交 `reviewEngine` 和 `agentSourceExportAllowed`。
- 前端在选择 `AGENT` 但未确认源码外发授权时直接阻止保存并提示。
- Agent 设置卡和“AI Review 配置”项目组策略区增加明确的切换路径、主引擎和 fallback 说明。
- 项目组策略区按“Review 引擎 → 触发与授权开关 → 修复预览 / Push 策略”重新分组：桌面端开关保持同一行，修复预览与 Push 策略并排，窄屏自动换行。

回归验证：

- 运行 `scripts/run-frontend.cmd build`。
- 打开 `/settings`，在“AI Review 配置”选择项目组，切换为 `AGENT`、确认源码外发授权并保存；刷新后确认两项保持，随后可用该项目的 Manual Review 验证请求引擎为 `AGENT`。

## BUG-20260724-002 Agent Review 设置提示重复且混用本地操作说明

状态：已修复

发现时间：2026-07-24

现象：

- Agent Review 设置卡同时展示固定组合、项目组切换、加密主密钥和历史配置测试成功等多条提示，主要配置区域被挤压。
- Linux Docker 环境缺少加密主密钥时仍提示执行 Windows 本地脚本。
- 历史配置测试成功提示会在刷新后持续显示，即使当前后端缺少加密主密钥，也可能同时出现“配置可用”和“不能保存 Key”。

修复：

- 删除固定组合和项目组切换两条常驻说明，相关状态继续由配置字段、Worker 标签和项目组策略区域表达。
- 配置测试成功仅使用即时消息反馈，不再把历史成功结果渲染为常驻 Alert；进行中、失败和超时仍保留状态提示。
- 缺少加密主密钥时只保留一条阻塞提示，统一说明在后端运行环境配置 `AGENT_REVIEW_CONFIG_ENCRYPTION_KEY` 并重启，不再混用 Windows 专属命令。

回归验证：

- 运行 `scripts/run-frontend.cmd build`。
- 打开 `/settings` 的 Agent Review 配置，确认正常状态没有常驻说明或历史成功 Alert；缺少加密主密钥时仅显示一条环境无关的阻塞提示。
