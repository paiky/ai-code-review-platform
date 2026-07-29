# Agent Review 多 Worker 池化与队列治理推进计划

## 1. 状态、目标与停止点

- 文档状态：三阶段路线已确认；阶段一“安全并发领取与租约 fencing”代码与本地自动化已完成，
  当前停止并等待用户确认是否进入阶段二。
- 当前基础：Agent Review 已使用 `code_quality_scheduler_jobs` 入队，具备优先级、数据库行锁、租约、
  心跳、重试次数、幂等完成和 Standard fallback。
- 总体目标：保持一个 Worker 容器同时只执行一个 Agent Review，通过多个独立 Worker 副本并发处理不同任务。
- 首次池化验收使用 2 个 Worker；MySQL 8 是生产并发验收前置条件，MySQL 5.7 只保留串行领取兼容。
- 本计划不引入 Redis、MQ、单 Worker 多任务、自动扩缩容或项目级并发配额。
- 每阶段完成代码、本地自动化和脱敏审计后必须停止；未经用户确认不得进入下一阶段。
- 整个计划不包含 Run 18。

## 2. 现状与必须先解决的问题

当前 Worker 主循环同步领取和执行任务，因此单实例并发度为 1。数据库领取在 MySQL 8 使用
`FOR UPDATE SKIP LOCKED`，理论上可由多个 Worker 同时领取不同任务，但直接扩容仍有以下风险：

1. Compose 使用静态 `AGENT_REVIEW_WORKER_ID`，多个副本会共享租约所有者身份。
2. Claim 没有把现有 `attempt` 作为租约代次传给 Worker，旧 Worker 的迟到请求无法与新尝试严格隔离。
3. 工具轨迹和心跳只按 `runId + sequence` 幂等，任务接管后序号从零开始会与旧尝试冲突。
4. Worker 执行普通任务时只上报 Job 心跳，不持续上报进程心跳；长任务期间全局 Worker 状态可能被误判离线。
5. 配置测试使用单例设置记录，但领取时没有数据库行锁，并发 Worker 可能重复执行。
6. Worker 在线状态保存在单例 Agent Settings 中，多个节点会互相覆盖，不能支持池级可观测。

前三项和配置测试竞争必须在扩容前解决；Worker 注册和池级展示在阶段二解决。

## 3. 总体架构与固定边界

```text
Review trigger
    -> MySQL scheduler queue
        -> Worker A: capacity=1
        -> Worker B: capacity=1
            -> job heartbeat / safe trace / terminal result
```

- 继续复用现有任务队列表和内部 Worker API 路径。
- 调度顺序保持 `priority DESC + queuedAt ASC`。
- Worker 共享现有内部 Token、DeepSeek Key、只读 workspace 和出站代理；每个容器拥有独立临时目录与
  Claude Code session。
- 不修改 DeepSeek 模型、Endpoint、Thinking Mode、预算安全上限、工具白名单、Review Card schema、
  Standard Review 或 Standard fallback。
- 不在轨迹、Worker 注册或队列指标中保存 Prompt、查询、工具参数、源码、diff、文件路径、模型原文或推理。

## 4. 阶段一：安全并发领取与租约 fencing

### 4.1 Worker 身份

- 显式 `AGENT_REVIEW_WORKER_ID` 继续用于本地单实例。
- 未显式配置时，使用 `AGENT_REVIEW_WORKER_ID_PREFIX`（默认 `agent-worker`）与容器 hostname 组成 ID。
- Worker ID 只允许字母、数字、点、下划线和连字符，长度为 1～128；非法值拒绝启动。
- 阶段一不修改 Compose，阶段二再移除生产环境的静态完整 ID。

### 4.2 Claim 与请求 fencing

- Backend Claim 成功后返回 `claimAttempt`，值为本次领取后现有 `job.attempt`。
- Worker 在 Job 心跳、完成、失败和取消请求中原样回传 `claimAttempt`。
- Backend 对未终态任务依次校验：
  - `idempotencyKey` 不匹配：`AGENT_IDEMPOTENCY_MISMATCH`；
  - `lease_owner` 不匹配：`AGENT_JOB_LEASE_LOST`；
  - `attempt` 不匹配：`AGENT_JOB_CLAIM_STALE`。
- 已成功进入终态的同一幂等完成/失败请求保持原有幂等返回，不再次修改结果。
- Claim、租约过期接管和 fencing 不提高 `max_attempts=2`。

### 4.3 时间轴隔离

- Agent 工具轨迹与安全心跳使用 `runId + claimAttempt + sequence` 幂等。
- 所有新轨迹 detail 增加非负整数 `claimAttempt`；旧事件缺失时按 `0` 兼容。
- 当 `claimAttempt > 1` 时，Backend 在该尝试首次轨迹或心跳之前追加一次 `AGENT_RECLAIMED`：
  - 只包含 `runId`、`claimAttempt`、固定 `reasonCode=LEASE_EXPIRED`；
  - 不包含 Worker ID、异常原文或基础设施地址。
- 前端按最新 `runId + claimAttempt` 聚合轨迹；旧 Agent Run、Standard Review 和没有 attempt 的任务保持兼容。

### 4.4 独立进程心跳与配置测试锁

- Worker 启动一个独立进程心跳线程，空闲和执行 Job 时均每 15 秒上报一次，退出时停止。
- Job 心跳继续独立续租并上报安全执行快照。
- 配置测试领取锁定 Agent Settings 单例行；并发 Claim 只有一个请求能把 `QUEUED` 改为 `RUNNING`。

### 4.5 阶段一停止点

只完成 Python Backend、Worker、时间轴兼容和对应测试。不得修改 Worker 注册表、Compose 副本、远程环境，
不得调用真实 Agent Review。完成本地验证后停止，等待用户确认阶段二。

### 4.6 阶段一实施结果（2026-07-29）

- Worker 支持显式 ID 或“固定前缀 + hostname”派生 ID，并在启动前校验长度与字符集。
- Claim 返回 `claimAttempt`；Job 心跳、完成、失败和取消均执行 owner、attempt 与幂等 fencing。
- 安全执行轨迹按 `runId + claimAttempt + sequence` 隔离，接管时只记录尝试次数和固定原因码。
- Worker 进程心跳与 Job 执行线程解耦，忙碌期间仍持续报告在线。
- 配置测试领取增加设置行锁；MySQL 8 `SKIP LOCKED` 的真实并发集成验收保留到阶段二。
- Backend 定向测试通过：`83 passed, 1 skipped`；Frontend 纯函数测试通过：`11 passed`；
  Frontend production build 通过。
- 未新增数据库表、公开 API 路径或外部依赖；未修改 Compose，未部署，未运行真实 Agent Review，
  未触发 Run 18。

## 5. 阶段二：Worker 注册与两副本池化

### 5.1 Worker 注册表

新增 `code_quality_agent_workers`：

| 字段 | 约束 |
| --- | --- |
| `worker_id` | `VARCHAR(128)` 主键 |
| `worker_version` / `cli_version` | 可空版本字符串 |
| `state` | `IDLE`、`BUSY`、`DRAINING` |
| `capacity` | 固定为 1 |
| `active_job_id` / `active_run_id` | 可空安全活动引用 |
| `started_at` | 节点本次启动时间 |
| `last_heartbeat_at` / `updated_at` | 心跳和更新时间 |

- 补充干净数据库 SQL、现有数据库运行时 schema 补齐和 `last_heartbeat_at` 索引。
- 在线状态按 60 秒窗口计算；离线记录保留 7 天后清理。
- 现有 Agent Settings Worker 字段不删除，作为旧版本兼容字段。

### 5.2 接口与前端

- 继续使用现有 Worker 心跳路径，上报 `state`、`capacity` 和安全活动引用。
- 扩展现有 Agent Settings GET，增加：
  - `workerPool.onlineCount`、`busyCount`、`idleCount`、`totalCapacity`；
  - 安全节点列表：Worker ID、状态、版本、容量、最近心跳。
- 现有 `workerStatus` 改为池级 ONLINE/OFFLINE，旧字段继续返回。
- 设置页增加 Worker Pool 区域；任务详情展示 attempt 和接管事件，不展示 Worker 基础设施详情。
- Worker 增加 `--healthcheck`，按自身派生 ID 验证注册状态。

### 5.3 两副本部署

- Compose 改用 Worker ID 前缀和容器 hostname，不设置静态完整 ID。
- 部署前确保没有 QUEUED/RUNNING Agent Job，禁用 Agent 并停止旧 Worker。
- 部署顺序：Backend/Schema → 两个 Agent Worker → Frontend → 重新启用 Agent。
- 使用 `docker compose up -d --scale agent-worker=2` 启动两个 capacity=1 的副本。
- 用户用两个独立的 1～5 文件小任务验证并发领取后停止；不得执行 Run 18。

## 6. 阶段三：队列运行治理

- 在现有 Agent Settings 响应和设置页展示 queued、running、expired lease、最老排队时长、在线容量和利用率。
- 在线 Worker 全部 BUSY 时任务继续排队，不得按“无 Worker”触发 fallback。
- Worker 收到 SIGTERM 后进入 DRAINING、停止 Claim，并让当前任务在既有 timeout 内结束；超过停机宽限期退出，
  由租约过期机制接管。
- 增加队列积压和 Worker 离线告警文案。
- 保持人工 Compose 扩缩容；自动扩缩容、项目级并发配额和单 Worker 多任务继续后置。
- 本阶段只用小任务验证扩缩容和故障接管，不执行 Run 18。

## 7. 测试与验收

阶段一：

- Worker ID 显式配置、hostname 派生和非法值拒绝；
- 两个并发 Claim 不能领取同一 Job；
- 租约接管后 `claimAttempt` 递增；
- 旧 Worker 的迟到心跳、完成、失败和取消请求稳定拒绝；
- 同一终态请求保持幂等；
- 时间轴按 attempt 隔离，接管事件保持数字/枚举白名单；
- 忙碌 Worker 的进程心跳持续上报；
- 配置测试并发领取只有一次。

阶段二：

- Worker 注册、状态切换、60 秒离线判断和 7 天清理；
- 池级兼容字段、单 Worker 和无注册表历史数据；
- 两副本健康检查、设置页 Worker Pool 和任务 attempt 展示；
- MySQL 8 `SKIP LOCKED` 并发领取集成测试。

阶段三：

- 队列统计、最老排队时长和容量利用率；
- 全部 Worker 忙碌时继续排队；
- SIGTERM draining、当前任务结束和租约接管；
- Standard、旧 Agent 和无池化数据任务兼容；
- Frontend production build。

所有阶段最终 diff 必须检查不含真实 Key、Prompt、源码、查询、路径、模型原文或推理。

## 8. 总控 Prompt

```text
请按 docs/47-agent-review-multi-worker-pool-and-queue-governance-plan.md 推进。

每次只能实施用户明确确认的一个阶段。开始前检查工作区并保留用户已有修改；先更新本文状态，再修改
Python Backend、Agent Worker、现有 React 前端和对应测试。Java 后端不在范围内。

不得修改模型、Endpoint、Thinking Mode、预算安全上限、工具白名单、Review Card schema、Standard Review
或 fallback；不得引入 Redis/MQ、单 Worker 多任务、自动扩缩容或新增公开 API 路径。

完成当前阶段代码、本地自动化、前端 build 和脱敏 diff 审计后必须停止。未经用户确认，不得部署、运行真实
Agent Review、进入下一阶段或触发 Run 18。
```

## 9. 分阶段实施 Prompt

### 阶段一 Prompt

```text
请只实施 docs/47 的阶段一“安全并发领取与租约 fencing”。

实现唯一 Worker ID、claimAttempt 全链路校验、attempt 维度时间轴、AGENT_RECLAIMED、独立进程心跳和配置
测试行锁。补充并发领取、迟到请求、幂等、心跳和脱敏测试。

不得新增 Worker 注册表、修改 Compose 副本、部署或执行真实 Agent Review。完成本地测试和前端 build 后停止。
```

### 阶段二 Prompt

```text
仅在用户确认阶段一后实施 docs/47 的阶段二“Worker 注册与两副本池化”。

新增 Worker 注册表、schema 兼容、池级设置响应、设置页 Worker Pool、Worker healthcheck 和 Compose 两副本支持。
本地自动化完成后停止，等待用户按 Backend/Schema → 两个 Worker → Frontend 顺序部署并执行两个小任务验收。

不得进入队列治理、自动扩缩容或 Run 18。
```

### 阶段三 Prompt

```text
仅在用户确认阶段二远程验收后实施 docs/47 的阶段三“队列运行治理”。

增加队列与容量指标、全部 Worker 忙碌时的正确排队语义、SIGTERM draining 和安全告警展示。保持人工 Compose
扩缩容，不实现项目级并发配额、单 Worker 多任务或自动扩缩容。

完成本地自动化后停止；远程只做小任务扩缩容和故障接管验收，不执行 Run 18。
```

## 10. 授权边界

允许修改：

- Python Agent Review Backend、Worker 和内部 Worker 契约；
- Agent 任务时间轴、设置页和对应测试；
- 阶段二所需初始化 SQL、运行时 schema 和 Compose；
- 本专题文档及必要中文注释。

禁止：

- Java 后端、DeepSeek 模型与 Endpoint、Thinking Mode、预算安全边界、工具权限；
- 新增公开 API 路径或引入 Redis、MQ 等外部依赖；
- 单 Worker 并行运行多个 Claude Code；
- 未经确认进入下一阶段、远程部署、真实 Agent Review 或 Run 18。
