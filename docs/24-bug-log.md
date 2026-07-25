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

## BUG-20260724-003 Agent fallback 页签重名且工作区失败原因被覆盖

状态：已修复

发现时间：2026-07-24

现象：

- 任务 `1015` 请求 `AGENT` 后降级到 `STANDARD_FALLBACK`，两个普通 Review 结果页签都显示为“Agent → 普通 Review”，无法区分实际执行的 GLM 与 DeepSeek。
- 项目 mirror 已成功 fetch，但事件提交已不在 mirror 中，任务 worktree 无法按精确 SHA 检出，Agent Run 未创建并记录 `AGENT_WORKTREE_UNAVAILABLE`。
- 本地引用搜索缺少 `rg` 时，会把已经准备好的仓库摘要覆盖成 `worktree MISSING`，掩盖真实失败阶段。

根因：

- 页签文案只判断请求引擎与实际引擎，没有在 fallback 后保留实际 Provider 名称。
- 临时分支或 force-push 分支可能在 webhook 到达后继续移动；普通 mirror fetch 只能获得服务器当前可达的 refs，事件 SHA 可能未被带回。
- 本地引用搜索不可用与 worktree 不存在共用同一段摘要覆盖逻辑。

修复：

- fallback 结果页签显示实际 Provider，并附带“Agent 降级”标识。
- 普通 fetch 后若精确 40 位提交 SHA 无法检出，额外按该 SHA 定向 fetch 一次并重试；仍不可达时保持失败，禁止改用分支最新提交代替。
- `rg` 不可执行时使用 `git grep` 作为本地引用搜索后备；Docker 后端镜像同时安装 `ripgrep`。
- 只有本地引用检索明确报告 worktree 不存在时才更新 worktree 摘要，搜索工具异常不再覆盖仓库准备结果。

回归验证：

- 运行 `scripts/run-backend.cmd test tests/unit/test_local_repo_context.py tests/unit/test_local_retriever.py tests/unit/test_review_context_pack.py`。
- 运行 `scripts/run-frontend.cmd build`。
- 对包含两个普通 Provider 的 Agent fallback 任务确认页签分别显示实际 Provider；用可定向获取的精确 SHA 验证 worktree 重试，用不可达 SHA 验证仍安全降级且保留真实原因。

## BUG-20260724-004 普通 Review 未复用可用的 Provider 出站代理

状态：已修复

发现时间：2026-07-24

现象：

- DeepSeek 普通 Review 或 Agent fallback 后的 DeepSeek 结果偶发失败，错误为 `connect_error: [Errno -2] Name or service not known`。
- 同一环境的 Agent 配置测试可用。

根因：

- `AGENT_REVIEW_UPSTREAM_PROXY` 只作用于隔离的 Agent Worker 出站链路。
- 普通 Review 由 Python backend 直接请求 Provider；backend 未配置 Provider 专用代理时仍依赖本机或容器 DNS，因此 Agent 可用不代表普通 DeepSeek 链路可用。

修复：

- 新增 `CODE_QUALITY_REVIEW_PROXY`，只用于普通 Review、Provider 连接测试和修复预览的模型 HTTP 请求。
- 本地未显式配置时兼容复用 `AGENT_REVIEW_UPSTREAM_PROXY`，避免同一台开发机重复填写代理；生产环境可分别配置两条链路。
- Docker Compose 将该变量传给 backend，不设置时保持原有直连行为；GitLab、钉钉和数据库请求不受影响。

回归验证：

- 配置 `CODE_QUALITY_REVIEW_PROXY=http://代理地址:端口` 并重启 backend。
- 在设置页测试 DeepSeek Provider，再重试普通 Review，确认不再出现本机 DNS 的 `Errno -2`。
