# Agent Review 运行可观测性与时间轴收敛计划

## 1. 状态与目标

- 文档状态：本地实现与自动化验证完成，待部署后小型真实任务验收。
- 前置条件：`docs/45-agent-review-runtime-budget-configuration-plan.md` 的自定义 `maxTurns`
  小型真实任务已成功验收。
- 本阶段目标：在不暴露模型思维链和源码的前提下，让任务详情能够可靠展示 Agent 当前阶段、
  最近心跳、预算消耗、重复工具活动摘要和最终结果。
- 本阶段完成代码、本地自动化与浏览器验证后停止；不部署、不执行真实 Agent Review、不触发 Run 18。

## 2. 事件与安全契约

继续使用现有进度事件表和 API，不新增数据库结构或公开路径。

可见 Agent 时间轴阶段：

```text
AGENT_ANALYZING
AGENT_TOOL_ACTIVITY
AGENT_CONVERGING
AGENT_SUBMITTING
AGENT_FINISHED
AGENT_FALLBACK
AGENT_CANCELLED
```

Worker 对运行中任务立即发送一次心跳，之后每 15 秒发送一次递增 `heartbeatSequence`。Backend 使用
`runId + heartbeatSequence` 幂等保存 `AGENT_HEARTBEAT` 辅助事件。心跳事件不直接铺入时间轴，只用于
刷新运行摘要和判断页面数据是否可能延迟。

所有 Agent 可观测性 detail 仅允许：

- `runId`、工具或心跳序号、阶段和固定活动枚举；
- 成功/失败状态、稳定错误码；
- duration、item count、tool/evidence/source/diff 数字；
- `reviewBudget` 与 `effectiveBudgets` 数字白名单；
- 文件后缀、目录深度等既有脱敏摘要；
- Backend 生成的心跳时间。

不得保存或展示 Prompt、搜索词、工具参数、源码、diff、相对或绝对路径、assistant 原文、模型推理、
API Key、query hash 或 path hash。

## 3. Backend 与 Worker

- Worker 心跳循环改为启动后立即上报，再以 15 秒为间隔上报；每次携带当前进程内递增序号。
- Backend 在续租成功后安全追加心跳事件，并保证同一 `runId + heartbeatSequence` 只保存一次。
- 首次心跳即补充 `AGENT_ANALYZING`，不等待第一次工具调用。
- 心跳 detail 从已脱敏 audit 和 Run 预算快照生成，只保留预算与计数。
- 正式完成、失败降级和取消继续使用现有终态事件，不改变主结果或 fallback。
- 心跳或轨迹落库失败必须回滚自己的可观测性写入，不能撤销已经成功的任务续租或改变主结果。

## 4. Frontend

- Agent 专属时间轴纳入成功、降级和取消终态。
- 连续相同阶段、活动和状态的工具事件折叠为一个摘要节点，显示覆盖序号和合计计数。
- 在时间轴顶部展示：
  - 当前 DISCOVERY / CONVERGE / SUBMIT 或终态；
  - tools、evidence、source bytes 的已用/上限；
  - turns 在运行中明确显示“CLI 完成前不可观测”，终态显示最终值；
  - 最近心跳时间。
- 运行中超过 45 秒没有新心跳时，只提示“进度数据可能延迟”，不得断言 Agent 卡死或伪造百分比。
- `AGENT_HEARTBEAT` 不作为独立时间轴节点，避免 10 分钟任务产生大量重复视觉噪音。
- Standard Review、旧 Agent Run 和没有心跳事件的历史任务保持现有展示。

## 5. 测试与停止点

Backend / Worker：

- 立即心跳、递增序号和当前脱敏 audit 上报；
- `runId + heartbeatSequence` 幂等；
- 首次心跳生成分析节点；
- 心跳 detail 数字白名单及敏感字段剔除；
- 可观测性落库失败不影响续租；
- 成功、降级和取消终态保持兼容。

Frontend：

- Standard、旧 Agent 和新 Agent 心跳兼容；
- 心跳摘要、45 秒延迟判断和终态排序；
- 连续工具活动合并；
- 预算已用/上限计算与 turns 不可观测提示；
- 脱敏格式化、production build 和本地响应式浏览器检查。

本阶段完成后停止并等待部署。部署并用 1～5 文件小任务确认时间轴后，才允许执行一次 Run 18 受控回归；
动态预算顺延到下一阶段。

## 6. 本地实施结果

- Backend / Worker 已实现启动即心跳、15 秒递增心跳、`runId + heartbeatSequence`
  幂等、安全白名单和不影响续租的失败隔离。
- Frontend 已实现当前阶段与预算摘要、45 秒进度延迟提示、连续工具活动合并和成功/降级/取消终态展示。
- Backend 定向测试：`68 passed, 1 skipped`。
- Frontend 预算与时间轴纯函数测试：`10 passed`。
- Frontend production build：通过；仅保留既有的大 chunk 提示。
- 本地页面可访问，但验证时 Backend 未启动，任务列表无法取得真实任务数据；因此未伪造时间轴数据，
  真实任务视觉与心跳刷新留待部署后使用 1～5 文件小任务验收。

停止点：不部署、不执行真实 Agent Review、不触发 Run 18，等待用户部署并确认下一阶段。
