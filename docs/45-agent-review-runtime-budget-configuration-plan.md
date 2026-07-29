# Agent Review 运行参数配置化与安全上限治理

## 1. 状态与目标

- 文档状态：已实现，待远程小型任务验收。
- 前置条件：`docs/44-agent-review-local-like-convergence-plan.md` 的小型真实 Agent Review 已完成验收。
- 本阶段目标：在不改变现有默认行为的前提下，为标准 Agent Review 增加全局运行预算配置，并由
  Backend 和 Agent Worker 双重执行安全上限。
- 本阶段停止点：完成代码、本地自动化测试和前端构建后必须停止，等待用户按
  Backend → Agent Worker → Frontend 顺序部署；不得执行真实 Agent Review、Run 18 或 high/max A/B。

## 2. 范围与边界

本阶段允许：

- 在现有 `code_quality_agent_settings` 增加一个可空预算 JSON 字段；
- 扩展现有 Agent Settings GET/PUT 响应和请求字段；
- 修改 Python Backend、Agent Worker、Runner、只读 MCP、React 设置页和任务详情；
- 增加干净数据库初始化 SQL、运行时兼容补列和对应测试。

本阶段不允许：

- 新增数据库表或公开 API 路径；
- 修改 DeepSeek 模型、Endpoint、Thinking Mode 或标准 `reasoningEffort=high`；
- 开放 Bash、Git、写文件、Web、子 Agent 或其它 MCP；
- 修改 STANDARD Review、普通 Review 高准确模式或现有 fallback；
- 保存 Prompt、工具参数、搜索词、源码、diff、绝对路径或模型推理；
- 自动执行远程部署、真实 Agent Review、Run 18 或动态预算。

## 3. 配置结构

全局预算仍使用现有 Agent Settings 单行记录。新增：

```text
code_quality_agent_settings.budget_config_json TEXT NULL
```

`NULL` 表示使用默认值；非空值保存经过 Backend 校验后的完整八项配置。新任务入队时把有效预算写入
现有 `AgentReviewRun.input_json` 的安全数字快照，配置变更不影响已排队或运行中的任务。旧 Run 没有快照时
继续使用默认值。

| 字段 | 默认值 | 最小值 | 绝对上限 | 中文说明 |
| --- | ---: | ---: | ---: | --- |
| `maxTurns` | 12 | 6 | 18 | Claude Code 模型决策回合上限 |
| `maxToolCalls` | 40 | 10 | 60 | 所有 MCP 工具调用上限 |
| `maxSourceBytes` | 200000 | 10000 | 300000 | 返回给模型的源码和分页 diff 总字节预算 |
| `timeoutSeconds` | 600 | 60 | 900 | Agent 子进程整体超时 |
| `inlineDiffBytes` | 200000 | 10000 | 300000 | 初始 Prompt 可内联的 diff 字节数 |
| `maxEvidenceCalls` | 10 | 4 | 15 | 搜索、读取源码和读取 diff 的调用上限 |
| `convergeAtCalls` | 8 | 2 | 13 | 从该次证据调用开始要求收敛 |
| `submitByTurn` | 9 | 3 | 15 | 最迟开始提交 Review Card 的模型回合 |

跨字段约束：

```text
convergeAtCalls <= maxEvidenceCalls - 2
submitByTurn <= maxTurns - 3
maxToolCalls >= maxEvidenceCalls + 1
```

`maxDiffBytes=1048576` 继续是不可编辑的输入硬上限。

## 4. 接口契约

继续使用：

```text
GET /api/code-quality-reviews/agent-settings
PUT /api/code-quality-reviews/agent-settings
```

GET 在现有字段基础上返回：

```json
{
  "budgets": {
    "maxTurns": 12,
    "maxToolCalls": 40,
    "maxSourceBytes": 200000,
    "timeoutSeconds": 600,
    "inlineDiffBytes": 200000,
    "maxEvidenceCalls": 10,
    "convergeAtCalls": 8,
    "submitByTurn": 9,
    "maxDiffBytes": 1048576
  },
  "budgetDefaults": {},
  "budgetLimits": {
    "maxTurns": {"min": 6, "max": 18}
  },
  "budgetConfigSource": "DEFAULT"
}
```

PUT 支持部分更新：

```json
{"budgets": {"maxTurns": 14}}
```

恢复默认：

```json
{"resetBudgets": true}
```

`budgets` 和 `resetBudgets=true` 不得同时提交。预算字段只接受 JSON 整数；布尔值、字符串、未知字段、
越界值和跨字段冲突统一返回 `VALIDATION_ERROR`。API Key、启用状态和预算在同一事务内更新。

## 5. 运行链路

1. Backend 读取并校验全局预算。
2. 入队时使用 `inlineDiffBytes` 决定 `INLINE` 或 `TOOL_PAGED`，并保存完整预算快照。
3. Worker claim 只返回该 Run 的快照；旧 Run 使用默认值，不读取后来修改的全局配置。
4. Worker 在创建 `RunnerConfig` 前按绝对上限再次严格校验；非法内部契约不截断，返回稳定失败并沿用
   `STANDARD_FALLBACK`。
5. Runner 将 `submitByTurn` 写入 Prompt，将证据预算通过 MCP 环境传入 `ToolBudget`。
6. 最终安全 Run 摘要只追加八项数字 `effectiveBudgets`，用于任务详情核验。
7. Agent 配置连通性测试继续使用固定 `4 turns / 8 tools / 10000 bytes / 180 seconds`，不读取生产预算。

## 6. 前端

- Agent 设置页把固定预算说明改成接口数据。
- 基础参数展示 turns、tools、源码 KB、超时、内联 diff KB。
- 高级参数展示证据次数、收敛起点和提交回合。
- 页面以 KB/秒展示，API 仍使用 bytes/seconds。
- 显示默认值、允许范围、跨字段错误、提高预算风险提示和“恢复默认”按钮。
- 任务详情 Agent 流转区展示该 Run 的 `effectiveBudgets`；Standard 和旧 Agent 任务没有快照时保持原展示。

## 7. 测试与验收

Backend：

- 默认、部分更新、完整更新、恢复默认和损坏存储安全回退；
- 字段类型、未知字段、上下限和三项跨字段约束；
- API Key 与预算原子保存及脱敏；
- 入队快照、配置变更不影响已排队任务、旧 Run 默认值；
- Worker 二次校验、动态 Prompt、动态 MCP 证据预算和 fallback；
- Run 摘要只包含预算数字白名单。

Frontend：

- bytes/KB 转换、草稿初始化、跨字段校验和恢复默认；
- Standard、旧 Agent 和带预算快照 Agent 的任务详情兼容；
- production build。

完成后检查最终 diff 不含真实 Key、源码、查询、工具参数或模型推理。远程验收由用户执行：先验证默认配置，
再把 `maxTurns` 调为 14 执行一个 1～5 文件的小型任务并恢复默认。该验收完成前不得执行 Run 18。

## 8. 单阶段实施 Prompt

```text
请实现 docs/45-agent-review-runtime-budget-configuration-plan.md，只推进一次“Agent Review 运行参数配置化与
安全上限治理”阶段。

先实现预算数据结构、设置接口和数据库兼容，再实现任务快照、Worker/Runner/MCP 双重校验，最后实现 React
设置页和任务详情。保持现有默认值，绝对上限与跨字段约束必须同时在 Backend 和 Worker 生效。

不得新增数据库表或 API 路径，不得修改模型、Endpoint、Thinking Mode、reasoningEffort、安全路径、工具白名单、
STANDARD Review 或 fallback。不得运行真实 Agent Review、远程部署或 Run 18。

完成定向测试和前端 build 后必须停止，报告改动、测试、风险和 Backend → Agent Worker → Frontend 部署顺序，
等待用户验收。
```

## 9. 总控授权边界与后续停止点

本阶段 Agent 可自主修改本文列出的 Python Backend、Agent Worker、React 前端、初始化 SQL、专题文档和对应测试；
不得扩大到项目组/Profile 继承、动态预算、深度 Review 档位或模型 A/B。

本阶段完成后必须停止。用户完成远程小型任务验收并明确确认后，下一阶段才可在以下方向中选择：

- Run 18 受控复杂任务回归；
- 基于 changed files 和 diff 规模的动态预算；
- STANDARD/AGENT 准确性比较；
- 标准 `high` 与深度 `max` 档位设计。

## 10. 本地实现与验证记录

2026-07-29 已完成单阶段实现：

- Agent Settings 以可空 JSON 保存八项全局预算，GET/PUT 支持部分更新、恢复默认、范围和跨字段校验；
- Agent 入队固化完整预算快照，旧 Run 使用原默认值，Worker 对 Claim 契约做第二次严格校验；
- Runner、收敛 Prompt 和只读 MCP 使用同一快照，最终摘要只保留八项数字白名单；
- React 设置页支持基础/高级参数、KB 换算、默认值与范围提示、风险提示和恢复默认；
- Agent 任务详情展示生效预算，Standard 和旧 Agent 任务保持兼容。

本地验证：

```text
scripts\run-backend.cmd test tests/unit/test_agent_review_budgets.py tests/unit/test_agent_review_spike_runner.py tests/unit/test_agent_review_spike_workspace.py tests/unit/test_agent_review_worker.py tests/contract/test_agent_review_api_contract.py
结果：78 passed, 1 skipped

node --test tests\agentReviewBudgets.test.mjs tests\agentReviewTrace.test.mjs
结果：7 passed

scripts\run-frontend.cmd build
结果：成功；仅保留既有大 chunk 告警
```

本地实现至此停止；未部署、未调用真实 DeepSeek Agent Review、未读取真实 API Key、未执行 Run 18。

## 11. 运行参数 UI 规整化

2026-07-29 根据本地设置页视觉检查，运行参数区域调整为分组等高参数卡片：

- 基础参数在宽屏使用五列等宽网格，中等屏幕降为三列或两列，移动端使用单列；
- 高级收敛参数继续折叠展示，展开后复用相同卡片结构；
- 每张卡片固定为参数名称、统一高度输入框、默认值和允许范围三层，避免标签与帮助文字换行造成错位；
- 说明文字和恢复默认操作合并到顶部工具栏，校验错误和预算风险提示保持原行为；
- 本次仅调整 React 布局与局部 CSS，不修改预算接口、换算、校验、保存逻辑或后端执行行为。

本地验证结果：

- 预算与轨迹纯函数测试 `7 passed`；
- `scripts\run-frontend.cmd build` 成功，仅保留既有大 chunk 告警；
- 浏览器检查确认 1434px 为基础五列/高级三列、1100px 为三列、900px 为两列、420px 为单列；
- 所有参数卡片等高，输入组合高度为 40px，单位框宽度为 58px，420px 视口无横向溢出。
