# Agent Review 多 Worker 池化与队列治理推进计划

## 1. 状态、目标与停止点

- 文档状态：三阶段路线已确认；阶段一“安全并发领取与租约 fencing”已完成并推送；
  阶段二“Worker 注册与两副本池化”已完成、推送并由用户确认远程两节点与双小任务并发验收通过；
  阶段三“队列运行治理”代码、本地自动化与一键部署助手已完成，当前停止并等待用户部署。
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

建议在远程 runtime 目录按以下顺序操作；执行前先在设置页禁用 Agent 并确认队列为空：

```bash
docker compose stop agent-worker
docker compose up -d backend
curl -fsS http://127.0.0.1:8090/api/code-quality-reviews/agent-settings >/dev/null
docker compose up -d --scale agent-worker=2 agent-egress-proxy agent-worker
docker compose up -d frontend
docker compose ps
```

确认设置页 Worker Pool 显示 2 个在线空闲节点后再重新启用 Agent。不得在两个 Worker 都未注册成功时提交验收任务。

### 5.4 阶段二实施结果（2026-07-29）

- 新增 `code_quality_agent_workers`、心跳索引、干净数据库 SQL 和运行时 schema 补齐；离线记录在后续心跳
  时清理 7 天前数据。
- Worker 心跳上报固定容量、IDLE/BUSY 状态和数字活动引用；Agent Settings 返回池级统计和安全节点白名单，
  同时保留原单例 Worker 字段兼容旧前端与历史数据。
- Worker 增加 `--healthcheck`，按自身派生 ID 检查注册记录；Linux Compose 只传 ID 前缀并使用容器
  hostname，避免旧环境中的显式 ID 破坏扩容唯一性；Windows 本地单实例仍允许可选显式 ID。
- 设置页增加 Worker Pool 汇总、节点状态、活动引用、版本和最近心跳；任务详情继续只显示领取尝试与接管事件。
- Backend 定向测试通过：`114 passed, 1 skipped`；Frontend 纯函数测试通过：`14 passed`；
  Frontend production build、三个 Compose 配置解析和 PowerShell 语法检查通过。
- 本机 `localhost:5173` 未运行，因此未做设置页运行时视觉检查；应在远程部署后与两节点注册一起确认。
- 未部署远程环境、未调用真实 DeepSeek、未执行真实 Agent Review，未触发 Run 18，未进入阶段三。
- 用户已确认远程环境中 `code_quality_agent_workers` 正常上线、两个 `capacity=1` Worker 正常注册，
  且两个独立小任务并发验收成功；阶段二提交 `4c37ea2` 已推送至 `origin/main`。

## 6. 阶段三：队列运行治理

### 6.1 Agent Settings 队列运行指标

继续使用 `GET/PUT /api/code-quality-reviews/agent-settings`，在响应中增加 `queueMetrics`，不新增公开路径、
数据库表或字段。所有队列数字从 `code_quality_scheduler_jobs` 实时安全聚合，Worker 容量从
`code_quality_agent_workers` 的白名单字段计算：

| 字段 | 固定定义 |
| --- | --- |
| `queued` | 仅统计 `job_type=AGENT_REVIEW AND status=QUEUED` |
| `running` | 仅统计 `job_type=AGENT_REVIEW AND status=RUNNING`，包含租约已过期但尚未接管的任务 |
| `expiredLease` | 仅统计 `job_type=AGENT_REVIEW AND status=RUNNING AND lease_expires_at < 当前时间` |
| `oldestQueuedSeconds` | 最早的有效 `queued_at` 到当前时间的整秒数；无队列、缺失、未来或损坏时间均安全返回 `0` |
| `onlineCapacity` | 60 秒在线窗口内、状态为 `IDLE/BUSY` 的节点容量之和；每节点容量固定为 `1`，排除 `DRAINING` |
| `busyCapacity` | 60 秒在线窗口内状态为 `BUSY` 的 capacity=1 节点容量之和 |
| `utilizationPercent` | `onlineCapacity=0` 时为 `0`；否则为 `busyCapacity / onlineCapacity * 100` 四舍五入整数，并限制在 `0..100` |
| `drainingWorkers` | 60 秒在线窗口内状态为 `DRAINING` 的 Worker 数量 |
| `lastWorkerHeartbeatAt` | 注册表最近一次安全心跳时间；无注册历史时兼容旧单 Worker 心跳，均不存在时为 `null` |

- `queueMetrics` 除心跳时间外只返回非负整数；损坏或历史数据回退为安全的 `0/null`。
- `workerPool` 继续保留阶段二兼容字段，并增加 `onlineCapacity`、`busyCapacity`、`utilizationPercent` 和
  `lastHeartbeatAt`；节点列表继续严格使用阶段二白名单，不增加基础设施、异常、Prompt、源码、diff、
  查询、工具参数、文件路径、模型原文或推理。
- 队列统计失败只影响设置页观测并安全回退，不得改变 Agent Review 的选择、执行、终态或 fallback 结果。

### 6.2 调度与全部 BUSY 语义

- Claim 顺序保持 `priority DESC + queued_at ASC`。
- `BUSY` 是在线且占用 capacity=1，不是离线。全部在线容量都为 `BUSY` 时，新 Agent 任务保持 `QUEUED`；
  不产生 `AGENT_REVIEW_UNAVAILABLE`，不触发 Standard fallback。
- Backend 对已注册为 `DRAINING` 的 Worker 拒绝继续 Claim；旧单 Worker或尚无注册记录的历史调用保持兼容。
- 不修改现有 `max_attempts=2`、租约续期、claimAttempt fencing、租约过期接管和 Standard fallback。

### 6.3 SIGTERM 优雅排空状态机

```text
IDLE --SIGTERM--> DRAINING --立即停止 Claim/上报一次最新状态--> EXIT
BUSY --SIGTERM--> DRAINING(active refs 保留)
     --当前任务在既有 Agent timeout 内完成并上报终态--> DRAINING(idle) --> EXIT
     --930 秒停机宽限期耗尽--> 强制退出 --> 现有租约过期 --> 其他 Worker 按 claimAttempt fencing 接管
```

- 首次 SIGTERM 原子设置排空状态和固定截止时间；重复信号幂等，不延长截止时间。
- DRAINING 立即停止发起新 Claim；已在途 Claim 若已由 Backend 成功领取，视为当前任务完成后退出。
- 进程心跳保持 15 秒周期并在状态切换时唤醒，持续上报 `DRAINING`；当前活动只保留数字 Job/Run 引用。
- 当前任务不因 SIGTERM 设置取消标记，不改变既有 Agent timeout、预算、工具白名单或终态逻辑。
- 固定停机宽限期为 `930` 秒：覆盖现有最大 `timeoutSeconds=900` 和最多 30 秒终态请求余量。
  三个 Compose 文件的 `stop_grace_period` 同步固定为 `930s`；宽限期耗尽后由进程退出与现有租约机制处理，
  不绕过 `max_attempts` 或 Standard fallback。
- 空闲 Worker 收到 SIGTERM 后直接退出；进程心跳或 DRAINING 上报失败只影响观测，不改变当前任务结果。

### 6.4 设置页固定告警阈值

- Worker Pool 无在线节点：错误告警，提示 Agent 任务可能在既有 60 秒离线宽限后进入既有 fallback。
- `drainingWorkers > 0`：警告正在排空，提示先补足容量再缩容。
- `expiredLease > 0`：警告等待租约接管，不展示 Worker、异常或模型原文。
- `queued > 0 AND busyCapacity >= onlineCapacity AND onlineCapacity > 0`：提示全部容量忙碌，任务会继续排队且
  不会仅因忙碌触发 fallback。
- 队列积压固定阈值：`queued >= 3` 或 `oldestQueuedSeconds >= 120` 时告警，提示使用人工命令
  `docker compose up -d --scale agent-worker=N` 扩容。
- 告警只由 GET 响应在前端派生，不落库、不调用通知、不改变 Agent Review 主结果。

### 6.5 阶段三停止点

- 保持人工 Compose 扩缩容；不实现自动扩缩容、项目级并发配额、单 Worker 多任务或动态资源预算。
- 本地代码、定向测试、Frontend production build、三个 Compose 解析、PowerShell 语法和脱敏审计完成后，
  回填本节实施结果并停止。
- 未经用户再次确认，不提交、不推送、不远程部署、不执行真实 Agent Review、小任务、Run 18 或下一阶段。

### 6.6 阶段三实施结果（2026-07-29）

- Agent Settings 增加实时安全聚合的 `queueMetrics`；只扫描 `AGENT_REVIEW` 的 `QUEUED/RUNNING` 活跃任务，
  返回排队、运行、过期租约、最老等待、在线/忙碌容量、整数利用率、排空节点数和最近心跳。
- Worker Pool 保留阶段二字段并增加容量指标；节点字段白名单未扩张，任务详情代码未修改，继续只展示
  `claimAttempt` 和脱敏 `AGENT_RECLAIMED`。
- Backend 在内部 Claim 入口拒绝已注册为 `DRAINING` 的 Worker；全部在线 Worker 为 `BUSY` 时仍保持
  ONLINE，新任务继续排队，既有离线宽限和 Standard fallback 未修改。
- Worker 增加幂等 SIGTERM 排空控制器、DRAINING 心跳唤醒、停止 Claim、当前任务完成后退出和 930 秒看门狗；
  三个 Compose 文件同步配置 `stop_grace_period: 930s`，Windows 操作脚本补充排空状态与队列摘要。
- 设置页增加队列摘要、容量利用率、最近心跳以及离线、排空、过期租约、全忙和固定阈值积压告警；
  旧 Backend 缺失 `queueMetrics` 时从现有 Worker Pool 安全兼容并把队列数字回退为 0。
- Backend/Worker 定向测试通过：`72 passed`；Frontend 全部纯函数测试通过：`17 passed`；
  Frontend production build 通过；三个 Compose 文件解析通过；PowerShell 脚本语法检查通过；
  本次 Python 文件定向 Ruff 检查通过。
- 仓库脚本的全量 lint 仍命中 5 个与本阶段无关的既有告警；按
  `docs/11-agent-environment-pitfalls.md` 已改用同一虚拟环境完成本次文件定向检查，未改动无关文件。
- 未新增数据库表、字段、公开 API、外部依赖或自动扩缩容；未修改模型、Endpoint、Thinking Mode、
  reasoningEffort、预算安全上限、工具白名单、Review Card schema、Standard Review 或 Standard fallback。
- 未提交、未推送、未远程部署、未执行真实 Agent Review、小任务或 Run 18。

### 6.7 未解决风险与阶段三远程验收

未解决风险：

- 本地自动化覆盖了状态机和租约接管，但真实 Docker SIGTERM 时序、15 秒 DRAINING 心跳可见性和 930 秒
  宽限仍需在远程小任务中确认。
- 队列聚合只查询现有 `status` 索引可缩小的活跃任务且不新增索引；生产历史数据规模下的设置页查询耗时
  尚未实测。指标查询失败会安全回退，不影响 Agent 主结果。
- Compose 自动缩容不保证优先选择空闲副本；验收 BUSY 排空时应按设置页安全数字引用定位容器，并使用
  定向 `docker stop`，不要用 Run 18 或大型任务。
- 本机未启动设置页做运行时视觉检查；production build 已通过，远程部署后仍需检查窄屏布局和告警文案。

建议部署顺序：

1. 在设置页禁用 Agent，确认 `queued=0`、`running=0`、`expiredLease=0`；旧 Worker 代码不支持排空，因此
   首次升级阶段三前必须等待现有任务结束。
2. 更新 Backend，确认 Agent Settings 同时返回兼容 `workerPool` 和新增 `queueMetrics`。
3. 停止旧 Worker，更新 Agent Worker 镜像，然后保持人工两副本：

   ```bash
   docker compose stop agent-worker
   docker compose up -d backend
   docker compose up -d --scale agent-worker=2 agent-egress-proxy agent-worker
   docker compose ps
   ```

4. 确认两个节点均为 `IDLE`、`onlineCapacity=2`、`busyCapacity=0`、`drainingWorkers=0` 后更新 Frontend。
5. 重新启用 Agent，只执行 1～5 文件的非敏感小任务；不得执行 Run 18。

扩容、缩容和故障接管小任务验收：

1. **扩容**：空队列时执行
   `docker compose up -d --scale agent-worker=3 agent-worker`；确认三个 capacity=1 节点在线且
   `onlineCapacity=3`。并发提交三个独立小任务，确认分别领取且利用率达到 100%。
2. **全忙排队**：三个 Worker 均 BUSY 时再提交第四个小任务；确认 `queued=1`、`busyCapacity=3`、
   `utilizationPercent=100`，任务没有 `AGENT_REVIEW_UNAVAILABLE` 或 Standard fallback；任一任务完成后第四个
   任务按 `priority DESC + queuedAt ASC` 被领取。
3. **空闲缩容**：确认待移除副本为空闲后执行
   `docker compose up -d --scale agent-worker=2 agent-worker`；确认该节点直接退出，最终
   `onlineCapacity=2`、`drainingWorkers=0` 且没有新增过期租约。
4. **BUSY 优雅排空**：用一个小任务占用目标副本，对该容器执行
   `docker stop --time 930 <agent-worker-container>`；确认节点变为 DRAINING、不再 Claim，当前任务在既有
   timeout 内正常完成且不触发 fallback，随后节点退出。再用人工 scale 命令恢复两个副本。
5. **故障接管**：用小任务占用一个副本后执行
   `docker rm -f <agent-worker-container>` 模拟不可优雅恢复的进程故障；确认 `expiredLease` 短暂增加，
   剩余 Worker 在租约过期后以递增 `claimAttempt` 接管，详情只出现脱敏 `AGENT_RECLAIMED`，最终仍遵守
   `max_attempts=2`。完成后用人工 scale 命令恢复两个副本。
6. 每个步骤完成后都先确认队列归零再继续；验收结束即停止，不执行大型任务、Run 18、自动扩缩容、
   项目级并发配额或单 Worker 多任务。

### 6.8 阶段三一键部署助手设计

离线部署包增加 `deploy-stage3.sh`，由现有 `load-images.sh` 一并复制到远程 runtime 目录。脚本只编排现有
Compose、Agent Settings GET/PUT 和 Worker Pool，不新增 API、数据库字段、依赖或自动扩缩容。

固定命令：

| 命令 | 行为 |
| --- | --- |
| `./deploy-stage3.sh status` | 只显示 enabled、queued、running、expiredLease、online/busy capacity、利用率与 draining 数量 |
| `./deploy-stage3.sh preflight` | 解析 Compose、检查 Backend 和安全指标；存在活跃/过期任务或零容量时非零退出 |
| `./deploy-stage3.sh upgrade --workers N` | 一键按 Backend → 队列闸门 → Worker N 副本 → Frontend → 恢复 Agent 执行 |
| `./deploy-stage3.sh scale --workers N` | 调用人工 Compose scale 并等待目标容量与 DRAINING 收敛，不做策略判断或自动扩缩容 |
| `--dry-run` | 只校验参数和 Compose，并打印将执行的变更，不修改容器或 Agent 设置 |

`upgrade` 状态机：

```text
加载镜像/更新 APP_VERSION（仍由 load-images.sh 完成）
  -> 更新 Backend 并等待 Agent Settings 可读
  -> 读取并只在内存保存原 enabled
  -> enabled=true 时等待 queued/running/expiredLease 全零
  -> PUT enabled=false 封闭新 Agent 入队竞态
  -> 再次确认队列全零；若竞态中出现新任务，恢复 enabled 并重新等待
  -> 更新 egress proxy 和 capacity=1 Worker，等待 onlineCapacity >= N 且 drainingWorkers=0
  -> 更新 Frontend
  -> 仅在 Backend 健康且目标容量满足时恢复原 enabled=true
  -> 输出最终安全数字
```

安全边界：

- 脚本不读取、输出或写入 API Key；PUT 只发送 `{"enabled": true/false}`，沿用现有保存语义。
- Agent Settings 响应只抽取固定布尔值和非负数字，不打印完整响应、节点、异常正文或模型内容。
- 任一步失败立即停止；如果脚本已经自动暂停 Agent，则保持禁用并输出恢复前置条件，不盲目重新启用。
- 使用进程锁阻止同一 runtime 的两个变更命令并发执行；`status/preflight` 保持只读。
- Worker 数量只接受 `1..100` 的显式整数，等待超时只接受 `60..3600` 秒；默认 `N=2`、超时 `1200` 秒。
- `scale` 仍是用户明确发起的人工扩缩容；脚本不根据指标自行改变副本数。
- 首次阶段二到阶段三升级必须使用默认安全模式；不提供旧 Worker 无 DRAINING 保护下的
  `--keep-agent-enabled` 冒险模式。

### 6.9 一键部署助手实施结果（2026-07-29）

- 新增 `deploy/deploy-stage3.sh`，实现 `status`、`preflight`、`upgrade`、`scale`、显式 Worker 数量、
  有界等待和 `--dry-run`；所有输出只包含固定状态和非负数字。
- `upgrade` 已实现 Backend 先行、零队列闸门、只修改 enabled 的暂停/恢复、Worker 目标容量等待、
  Frontend 最后更新和失败保持禁用；未实现 `--keep-agent-enabled`、自动扩缩容或自动回滚数据库。
- `scripts/package-docker-deploy.ps1` 会把助手写入离线包；`load-images.sh` 会复制到 runtime、设置可执行权限，
  并把默认提示从直接 `docker compose up -d` 调整为
  `./deploy-stage3.sh upgrade --workers 2`，保留直接 Compose 作为人工恢复手段。
- `docs/42-development-deployment-and-validation-guide.md` 已更新离线包清单、默认升级命令和常用只读/扩缩容命令。
- Bash `-n` 语法检查通过；禁网临时容器中的 `--dry-run` 通过；使用假 Compose 与固定安全数字的完整
  `enabled=true -> 暂停 -> 容量恢复 -> enabled=true` 状态机模拟通过；PowerShell 打包脚本语法通过；
  Backend/Worker 合并定向测试 `72 passed`，本次 Python 文件 Ruff 检查通过。
- 未实际构建离线镜像包、未访问真实 `.env`、未调用远程 Agent Settings、未修改真实 enabled、
  未部署、未运行真实 Agent Review 或 Run 18。
- 首次远程使用前先在 runtime 执行 `./deploy-stage3.sh upgrade --workers 2 --dry-run`；确认输出后再去掉
  `--dry-run`。如失败提示 Agent 保持禁用，必须先用 `status` 确认 Backend 和目标容量恢复，再由设置页
  人工恢复，不要绕过安全闸门。

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
