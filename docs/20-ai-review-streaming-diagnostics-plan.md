# AI Review 流式诊断与模型输出改造方案

> **状态：已暂停。** 当前实现为非流式 Provider HTTP 调用 + 前端轮询 `code-quality-progress` / `code-quality-result`；本文仅作历史方案参考，**不要继续按本文推进**。

日期：2026-05-19

## 0. Agent 执行入口与推进规则

本文件是 AI Review 流式诊断改造的自包含执行文档。后续 Agent 可以只阅读本文件并按第 16 节的分阶段 prompt 或第 17 节的总控 prompt 推进；如果需要理解项目通用约束，再补充阅读 `AGENTS.md`、`README.md` 和 `docs/10-local-dev-pitfalls.md`。

推进规则：

1. 每次只推进一个阶段，不要跨阶段实现。
2. 每个阶段开始前先说明阶段目标和本阶段不做事项。
3. 每个阶段完成后必须给出：改了什么、为什么、如何验证、剩余风险、下一阶段建议。
4. 每个阶段完成后必须停止，等待用户验证并明确确认“继续下一阶段”后再推进。
5. 如果使用第 17 节总控 prompt，Agent 可以按阶段自主推进，但仍必须遵守“阶段结束后停止等待确认”。
6. 遇到真实模型凭据、真实 GitLab、钉钉、Docker/network 权限、数据库密码或生产配置需求，先使用 mock 或本地配置；无法继续时停下来说明需要什么。
7. 不要把 API Key、GitLab token、DingTalk webhook 写入代码、日志、测试快照或文档。

## 1. 背景与问题

当前 Python 后端已经支持 OpenAI Responses、Anthropic Messages、DeepSeek / Custom OpenAI-compatible Chat Completions 等 Provider。当前真实接入重点是 OpenAI、DeepSeek 和 Custom OpenAI-compatible；Anthropic 暂时只保持现有非流式能力，不纳入本轮 token streaming 改造范围。实际接入多个模型后出现差异：

- 有些模型可以正常返回结构化 Review。
- 有些模型长时间无响应或最终失败。
- 前端只能看到已落库的 progress 轮询结果，不容易判断卡在请求构造、HTTP 连接、模型首包、响应解析还是结果保存。
- 不同 Provider 对 `stream`、`response_format`、JSON schema、endpoint URL 的支持程度不同，非流式接口失败时可观测性不足。

核心问题不是“必须马上看到逐 token 输出”，而是先要知道 AI Review 卡在哪一步。因此本方案将流式能力分成两层：

1. **执行过程流式诊断**：通过 SSE 实时推送 progress event，定位卡点。
2. **模型响应流式输出**：在诊断链路稳定后，再逐步适配各 Provider 的 token / delta stream。

## 2. 当前链路

```text
manual / retry / MR auto
  -> 创建或更新 review task
  -> 写入 code_quality_review_results RUNNING
  -> 写入 code_quality_review_progress_events QUEUED
  -> 后台线程执行 Provider
  -> REQUEST_BUILT
  -> *_REQUEST
  -> HTTP call model
  -> *_RESPONSE
  -> *_PARSED / *_PARSE_RESULT
  -> SAVE_RESULT
  -> FINISHED / FAILED
  -> 前端轮询 progress/result
```

现有能力：

- progress event 已落库。
- `/api/review-tasks/{taskId}/code-quality-progress` 可查询历史进度。
- manual / retry 已改为快速返回 `RUNNING`，Provider 在后台执行。
- Provider 调用前后已有部分请求、响应、解析事件。

当前缺口：

- 没有实时推送接口。
- progress 查询依赖前端轮询，慢模型下用户只能反复刷新。
- Provider 调用处缺少统一的 timeout 阶段语义，例如 connect timeout、first byte timeout、idle timeout。
- 模型原始输出无法边生成边观察。
- OpenAI-compatible 不同模型对 `response_format={"type":"json_object"}` 支持不同，失败时需要更清楚的协议诊断。

## 3. 目标行为

### 3.1 用户视角

触发 AI Review 后，前端应实时显示：

```text
当前阶段：HTTP_REQUEST_START
Provider：DEEPSEEK
Endpoint：https://api.deepseek.com/chat/completions
Model：deepseek-v4-pro
已等待：83 秒
最后事件：已发起 HTTP 请求，等待模型首包
```

模型返回时，前端应继续显示：

```text
HTTP_RESPONSE_HEADERS
HTTP_STREAM_DELTA
OUTPUT_EXTRACTED
JSON_PARSE_START
RESULT_SAVED
FINISHED
```

失败时，前端应显示可解释原因：

```text
Provider request timed out after 1000 seconds at HTTP_REQUEST_START.
可能原因：endpoint 不通、模型无响应、网络超时或 API 网关阻塞。
```

### 3.2 系统视角

必须满足：

- 现有轮询接口继续保留，SSE 只是增强能力。
- SSE 断开不影响后台 AI Review 执行。
- Progress event 仍然落库，刷新页面后能看到历史过程。
- API Key、Authorization header、token、secret、password 不进入响应、日志、progress、rawOutput。
- Provider 失败必须落成 `FAILED`，不能长期停在 `RUNNING`。
- 不同 Provider 可以分阶段接入真正 token streaming。
- 本轮 token streaming 只考虑 OpenAI、DeepSeek、Custom；Anthropic 不新增流式输出适配。

## 4. 总体设计

```text
Frontend Task Detail
  -> POST manual / retry
  -> EventSource /api/review-tasks/{taskId}/code-quality-progress/stream
      <- progress events from DB tail
      <- optional model delta events
      <- done / failed
  -> fallback polling /api/review-tasks/{taskId}/code-quality-progress
  -> polling or final fetch /api/review-tasks/{taskId}/code-quality-result

Backend
  -> progress repository append
  -> SSE stream endpoint tails DB by last event id
  -> Provider emits normalized stream events
  -> final result saved to code_quality_review_results
```

核心原则：

- **先实时化 progress，再流式化模型输出。**
- **所有事件都归一为平台事件，不直接把各厂商事件透给前端。**
- **模型 delta 可以不全量落库，但关键阶段和最终原文摘要必须落库。**
- **不把 SSE 当任务队列。后台任务仍由 executor 管理。**

## 5. 新增 API 契约

### 5.1 Progress SSE

```http
GET /api/review-tasks/{taskId}/code-quality-progress/stream
Accept: text/event-stream
```

查询参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `lastEventId` | long | 0 | 客户端已收到的最后 progress event id，断线重连时使用 |
| `includeSnapshot` | boolean | true | 首次连接是否先返回已有历史事件 |
| `heartbeatSeconds` | int | 15 | 心跳间隔，后端可限制范围 |

事件类型：

```text
event: progress
id: 1024
data: {"id":1024,"taskId":47,"phase":"REQUEST_BUILT","level":"INFO","message":"AI Review 请求已构建","detail":"provider=DEEPSEEK, model=...","createdAt":"2026-05-19T10:00:00"}

event: delta
data: {"taskId":47,"provider":"DEEPSEEK","text":"发现","sequence":1}

event: heartbeat
data: {"taskId":47,"serverTime":"2026-05-19T10:00:15"}

event: done
data: {"taskId":47,"status":"SUCCESS","resultAvailable":true}

event: failed
data: {"taskId":47,"status":"FAILED","errorMessage":"Provider request timed out after 1000 seconds at HTTP_REQUEST_START"}
```

### 5.2 兼容要求

- `progress` event 必须来自 `code_quality_review_progress_events`，可刷新恢复。
- `delta` event 可以只存在于 SSE 会话，不要求全部落库；如果需要排障，可按截断策略落库到 progress detail。
- `done` / `failed` 以 `code_quality_review_results.status` 为准。
- 客户端断线重连时通过 `Last-Event-ID` header 或 `lastEventId` 查询参数恢复。

## 6. 后端改动设计

### 6.1 新增模块建议

```text
backend-python/app/code_quality/
  progress_stream.py        # SSE endpoint/helper
  stream_events.py          # 统一事件模型
  stream_buffer.py          # 可选：进程内 delta fan-out
  providers_streaming.py    # 可选：流式 Provider 适配拆分
```

也可以先小步落在现有 `api.py`、`service.py`、`providers.py`，等稳定后再拆模块。

### 6.2 统一事件模型

建议内部事件结构：

```python
class CodeQualityStreamEvent:
    task_id: int
    type: Literal["progress", "delta", "raw", "parsed", "error", "done"]
    phase: str
    level: Literal["DEBUG", "INFO", "WARN", "ERROR"]
    message: str
    detail: dict | str | None
    text: str | None
    sequence: int | None
    persist: bool
```

落库规则：

| 类型 | 是否落库 | 说明 |
| --- | --- | --- |
| `progress` | 是 | 阶段事件，刷新可恢复 |
| `delta` | 默认否 | token 文本可能很大，先只前端展示 |
| `raw` | 截断后可落库 | HTTP body / provider event 预览 |
| `parsed` | 是 | 解析完成摘要 |
| `error` | 是 | 失败原因必须可恢复 |
| `done` | 否 | 可由 result status 推导 |

### 6.3 SSE 实现方式

推荐 FastAPI `StreamingResponse`：

```python
@router.get("/review-tasks/{task_id}/code-quality-progress/stream")
async def stream_code_quality_progress(task_id: int, last_event_id: int = 0):
    return StreamingResponse(
        event_generator(task_id, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

第一版可以采用 DB tail：

```text
while not terminal:
  query progress events where id > last_id order by id asc
  yield progress events
  query result status
  if SUCCESS / FAILED yield done/failed and break
  yield heartbeat if needed
  sleep 1s
```

优点：

- 实现简单。
- 不需要 Redis / 消息队列。
- 进程重启后仍能恢复历史 progress。

限制：

- 只适合当前 MVP 的低并发。
- 真正 token delta 如果不落库，需要进程内 fan-out，DB tail 看不到逐 token。

### 6.4 任务状态超时

新增阶段标识：

```text
PROVIDER_SELECTED
REQUEST_VALIDATED
REQUEST_BUILT
REQUEST_PREVIEW
HTTP_REQUEST_START
HTTP_RESPONSE_HEADERS
HTTP_RESPONSE_BODY_PREVIEW
STREAM_START
STREAM_DELTA
STREAM_DONE
OUTPUT_EXTRACTED
JSON_PARSE_START
JSON_PARSE_FAILED
RESULT_SAVED
FINISHED
FAILED
```

Provider 调用必须区分：

- `connect_timeout`：连接 endpoint 失败。
- `read_timeout`：连接成功但读取响应超时。
- `first_byte_timeout`：流式模式下长时间没有首个事件。
- `idle_timeout`：流式模式下两次 delta 间隔过长。
- `total_timeout`：总耗时超过上限。
- `protocol_error`：响应不是预期 SSE / JSON。
- `parse_error`：模型内容提取成功，但结构化 JSON 解析失败。

## 7. Provider 流式适配规划

### 7.1 OpenAI-compatible Chat Completions

适用：

- DeepSeek
- Custom OpenAI-compatible
- 其他兼容 `/chat/completions` 的模型网关

请求变化：

```json
{
  "model": "xxx",
  "stream": true,
  "messages": []
}
```

可选策略：

- 默认保留 `response_format={"type":"json_object"}`。
- 如果 Provider 返回 400 且错误显示不支持 `response_format`，可按配置 fallback 为非 `response_format`，但 prompt 必须强约束 JSON。
- `CUSTOM` Provider 增加可配置项：`supportsResponseFormat`、`supportsStreaming`，避免盲试。

流解析：

```text
data: {"choices":[{"delta":{"content":"..."}}]}
data: [DONE]
```

结束后：

- 拼接完整 `content`。
- 去除 ```json fence。
- 解析成平台 `CodeQualityReviewResult`。
- 保存 rawOutput 截断后的完整输出。

### 7.2 OpenAI Responses API

请求变化：

```json
{
  "model": "xxx",
  "instructions": "...",
  "input": "...",
  "text": {"format": {...}},
  "stream": true,
  "store": false
}
```

事件处理应兼容至少以下类别：

- response output text delta
- response completed
- response failed / error

最终仍以拼接出的 output text 走统一 JSON parse。

注意：

- 事件名称可能随 OpenAI API 版本变化，落地前需以官方文档和实际响应为准。
- 如果 Responses streaming 与 strict structured outputs 存在模型限制，先保留非流式 OpenAI，仅做 progress SSE。

### 7.3 Anthropic Messages（暂缓）

Anthropic 暂时不做 token streaming。要求：

- 保留现有 Anthropic 非流式接口，不破坏已有配置和查询能力。
- Progress SSE 对所有 Provider 通用，因此 Anthropic 非流式执行过程仍可通过 progress 事件观察。
- 不新增 Anthropic `stream=true`、`content_block_delta` 等流式协议适配。
- 后续如重新纳入范围，可单独增加 Anthropic Messages streaming 阶段。

后续候选请求形态：

```json
{
  "model": "xxx",
  "max_tokens": 4096,
  "system": "...",
  "messages": [],
  "stream": true
}
```

后续候选事件处理：

- `message_start`
- `content_block_start`
- `content_block_delta`
- `content_block_stop`
- `message_delta`
- `message_stop`
- `error`

如果未来落地 Anthropic streaming，最终仍需拼接 `text_delta`，再统一 JSON parse。

### 7.4 Provider 能力配置

建议 `code_quality_model_providers` 后续增加配置 JSON，而不是为每个能力加列：

```json
{
  "supportsStreaming": true,
  "supportsResponseFormat": true,
  "streamingProtocol": "OPENAI_CHAT_SSE",
  "firstByteTimeoutSeconds": 30,
  "idleTimeoutSeconds": 60,
  "disableResponseFormatFallback": false
}
```

短期不改表也可以先用环境变量或内置映射：

```text
OPENAI: supportsStreaming=false/true by implementation phase
ANTHROPIC: supportsStreaming=false，本轮不做 token streaming
DEEPSEEK: supportsStreaming=true
CUSTOM: default false，需要用户显式开启
```

## 8. 前端改动设计

### 8.1 数据访问

新增 API helper：

```javascript
function subscribeCodeQualityProgress(taskId, { onProgress, onDelta, onDone, onError }) {
  const source = new EventSource(`/api/review-tasks/${taskId}/code-quality-progress/stream`);
  ...
}
```

保留现有轮询：

- EventSource 不可用时 fallback。
- SSE 断线超过 N 次后 fallback。
- 页面不可见时可以降低轮询频率或关闭 SSE。

### 8.2 页面展示

任务详情页 AI Review tab 建议分成：

```text
代码质量 Review
  - 状态摘要
  - 实时阶段
  - 执行过程 Timeline
  - 模型输出预览
  - 最终 Finding 列表
```

执行过程 Timeline：

- 按 progress event id 顺序展示。
- `DEBUG` 默认折叠。
- `ERROR` 高亮。
- detail 支持复制，但继续展示脱敏内容。

模型输出预览：

- delta 流式追加。
- 最多展示前 N 字符，避免页面卡顿。
- 完成后用最终 result 替换或折叠。

卡点提示：

```text
如果最后阶段是 HTTP_REQUEST_START 且超过 60 秒：
提示“模型服务已连接或正在等待响应，可能是模型首包慢、endpoint 不通或网关阻塞。”

如果最后阶段是 JSON_PARSE_FAILED：
提示“模型已返回内容，但不是平台要求的 JSON，可查看原始响应预览。”
```

## 9. 安全与脱敏

必须脱敏：

- `Authorization`
- `x-api-key`
- `apiKey`
- `api_key`
- `token`
- `secret`
- `password`
- GitLab token
- DingTalk webhook token
- endpoint URL query 中疑似 token 参数

截断策略：

| 内容 | 最大长度 |
| --- | --- |
| request preview | 3000 chars |
| response raw preview | 3000 chars |
| output text preview | 3000 chars |
| progress detail | 4000 chars |
| SSE delta buffer | 前端最多保留 20000 chars |

注意：

- 不要把完整 diff 重复写入 progress。
- 不要把完整 raw model response 长期写入 progress。
- `rawOutput` 可以保存最终模型输出，但仍需脱敏和长度控制。

## 10. 配置项建议

```text
CODE_QUALITY_PROGRESS_STREAM_ENABLED=true
CODE_QUALITY_STREAMING_PROVIDER_ENABLED=false
CODE_QUALITY_STREAM_FIRST_BYTE_TIMEOUT_SECONDS=30
CODE_QUALITY_STREAM_IDLE_TIMEOUT_SECONDS=60
CODE_QUALITY_STREAM_TOTAL_TIMEOUT_SECONDS=180
CODE_QUALITY_PROGRESS_STREAM_POLL_INTERVAL_MS=1000
CODE_QUALITY_PROGRESS_STREAM_HEARTBEAT_SECONDS=15
CODE_QUALITY_RAW_PREVIEW_MAX_CHARS=3000
```

默认策略：

- progress SSE 默认开启。
- 模型 token streaming 默认关闭，按 Provider 逐步开启。
- 真实 Provider token streaming 未完成前，不影响现有非流式调用。

## 11. 分阶段落地

### 阶段 1：Progress SSE 只读流

目标：不改 Provider，只把已落库 progress 实时推给前端。

改动：

1. 新增 `GET /api/review-tasks/{taskId}/code-quality-progress/stream`。
2. SSE endpoint 通过 DB tail 推送 progress。
3. 终态 result 出现 `SUCCESS/FAILED` 后推送 `done/failed` 并结束。
4. 前端 AI Review tab 优先使用 SSE，失败 fallback 到轮询。
5. 补测试覆盖历史 snapshot、增量事件、终态事件、任务不存在。

验收：

- 触发 manual review 后页面无需刷新即可看到 `QUEUED`、`REQUEST_BUILT` 等事件。
- 关闭浏览器不影响后台任务。
- 刷新页面后仍能看到历史 progress。

### 阶段 2：Provider 诊断事件标准化

目标：不做 token stream，先把卡点定位清楚。

改动：

1. Provider 调用统一补 `PROVIDER_SELECTED`、`REQUEST_VALIDATED`、`HTTP_REQUEST_START`、`HTTP_RESPONSE_HEADERS`、`JSON_PARSE_START` 等阶段。
2. 区分 HTTP status error、connect/read timeout、非 JSON、空输出。
3. 错误结果写入 `code_quality_review_results.status=FAILED`。
4. 前端根据最后 phase 给出卡点提示。

验收：

- endpoint 错误、API key 错误、模型返回非 JSON、超时，都能在页面看到明确阶段和原因。
- 失败不会卡在 `RUNNING`。

### 阶段 3：OpenAI-compatible token stream

目标：优先支持 DeepSeek / Custom 的 Chat Completions SSE。

改动：

1. 增加 OpenAI-compatible streaming 调用路径。
2. 支持 `stream=true` 解析 `choices[].delta.content`。
3. SSE 向前端推送 `delta`。
4. 拼接完整文本后走现有 JSON parse 和结果保存。
5. 增加 Provider 配置开关，默认仅 DeepSeek 可开启，Custom 需手动开启。

验收：

- DeepSeek mock SSE 能实时显示模型输出。
- `[DONE]` 后保存结构化 findings。
- 非 JSON 输出保存 `FAILED`，并展示输出预览。

### 阶段 4：OpenAI Responses streaming

目标：适配 OpenAI Responses 的流式事件。

改动：

1. OpenAI Provider 增加 streaming 分支。
2. 解析 Responses streaming text delta / completed / error。
3. 保留 strict JSON schema，不支持时自动回退非流式或提示配置不支持。

验收：

- OpenAI mock stream 可产生 delta。
- 完成后 findings 与非流式结构一致。

### 阶段 5：配置化与运维收口

目标：把 Provider 能力、超时、fallback 策略配置化，并明确 Anthropic 暂缓。

改动：

1. 增加 Provider capability 配置。
2. 前端 Provider 设置页展示是否支持 streaming / response_format。
3. README 补充排障步骤。
4. docs/10-local-dev-pitfalls.md 补充流式常见坑。
5. Anthropic 展示为“非流式可用 / 流式暂未启用”，避免误导。

验收：

- 用户能知道某个模型是否启用流式。
- 关闭流式后仍使用稳定的非流式路径。
- Anthropic 现有非流式能力不被破坏。

## 12. 测试计划

### 12.1 后端测试

新增测试建议：

- `test_code_quality_progress_stream_snapshot`
- `test_code_quality_progress_stream_incremental_events`
- `test_code_quality_progress_stream_done_event`
- `test_code_quality_progress_stream_failed_event`
- `test_openai_compatible_stream_success`
- `test_openai_compatible_stream_non_json_failed`
- `test_openai_compatible_stream_idle_timeout`
- `test_openai_stream_success`
- `test_stream_events_do_not_leak_api_key`

使用：

- `pytest`
- `respx`
- mock SSE response body
- FastAPI `TestClient.stream`

### 12.2 前端测试 / 验证

最小验证：

- EventSource 连接成功时显示实时 timeline。
- EventSource 失败时回退轮询。
- 页面刷新后恢复历史 progress。
- 任务完成后自动刷新 result。
- 长 detail 和 delta 不撑爆页面。

构建验证：

```powershell
.\scripts\run-frontend.cmd build
```

### 12.3 手动联调矩阵

| Provider | 非流式 | Progress SSE | Token stream | 备注 |
| --- | --- | --- | --- | --- |
| OpenAI | 必须可用 | 必须可用 | 阶段 4 | 以 Responses API 为准 |
| Anthropic | 保持现有能力 | 必须可用 | 暂缓 | 本轮不做 Anthropic token streaming |
| DeepSeek | 必须可用 | 必须可用 | 阶段 3 | OpenAI-compatible |
| Custom | 必须可用 | 必须可用 | 手动开启 | 取决于网关能力 |

## 13. 失败场景与用户提示

| 最后 phase | 可能原因 | 前端提示 |
| --- | --- | --- |
| `REQUEST_VALIDATED` | 参数缺失、空 diff、Provider 禁用 | 请求未通过校验，请检查配置 |
| `HTTP_REQUEST_START` | endpoint 不通、DNS、网关阻塞、模型首包慢 | 已发起请求但未收到响应，请检查 endpoint 和网络 |
| `HTTP_RESPONSE_HEADERS` | 响应体读取慢、服务端流中断 | 已收到响应头，等待响应内容 |
| `HTTP_RESPONSE_BODY_PREVIEW` | 返回错误 JSON 或 HTML | 模型服务返回非预期内容 |
| `OUTPUT_EXTRACTED` | 模型内容不是平台 JSON | 模型已返回文本，但结构不符合要求 |
| `JSON_PARSE_FAILED` | prompt 约束不足、模型不支持 JSON mode | 解析失败，请查看原始输出预览 |
| `SAVE_RESULT` | 数据库写入异常 | 结果保存失败，请检查数据库 |

## 14. 风险与取舍

| 风险 | 等级 | 应对 |
| --- | --- | --- |
| SSE 长连接占用 worker | 中 | MVP 低并发可接受，生产用 gunicorn 多 worker 或异步 DB |
| DB tail 轮询增加数据库压力 | 中 | 只对打开详情页任务启用，轮询间隔 1s，可后续 Redis/pubsub |
| token delta 太大导致前端卡顿 | 中 | 前端截断和批量刷新 |
| Provider streaming 协议不一致 | 高 | 逐 Provider 适配，保留非流式 fallback |
| 流式输出不是合法 JSON | 高 | 最终仍统一 parse，失败落库并显示 raw preview |
| 敏感信息泄露 | 高 | 统一 scrub，测试覆盖 |

## 15. 不做事项

本轮不做：

- 不引入 Celery / Redis 队列。
- 不把 SSE 作为任务执行通道。
- 不强制所有 Provider 开启 token streaming。
- 不取消现有 progress 轮询接口。
- 不将完整模型 token 全量落库。
- 不自动修改真实 Provider 配置或 API Key。

## 16. 分阶段落地 Prompt

本节提供可直接复制使用的分阶段 prompt。原则是每个 prompt 只推进一个阶段，完成后必须停止并等待用户验证确认。不要用单个阶段 prompt 一次性完成全部流式改造。

### 16.1 阶段 1：Progress SSE 只读流

```text
请按 docs/20-ai-review-streaming-diagnostics-plan.md 落地阶段 1：Progress SSE 只读流。

要求：
1. 先阅读 docs/20-ai-review-streaming-diagnostics-plan.md；如需项目通用约束，再阅读 AGENTS.md、README.md、docs/10-local-dev-pitfalls.md。
2. 只做 Progress SSE，不改 Provider token streaming。
3. 新增 GET /api/review-tasks/{taskId}/code-quality-progress/stream，使用 text/event-stream。
4. SSE 先返回已有 progress snapshot，再 tail 新 progress event。
5. 任务结果进入 SUCCESS/FAILED 后发送 done/failed 事件并结束。
6. 前端 AI Review 执行过程优先使用 EventSource，失败时 fallback 到现有轮询。
7. 保留现有 /api/review-tasks/{taskId}/code-quality-progress 接口。
8. 所有事件 detail 继续脱敏。
9. 补 pytest 和前端构建验证。

完成后说明：改了什么、为什么、如何验证、剩余风险、下一阶段建议。
完成后停止，等待我验证并确认“继续下一阶段”后再推进。
```

### 16.2 阶段 2：Provider 诊断事件标准化

```text
请按 docs/20-ai-review-streaming-diagnostics-plan.md 落地阶段 2：Provider 诊断事件标准化。

前置条件：
1. 阶段 1 Progress SSE 已完成并通过验证。
2. 本阶段不做模型 token streaming。

Provider 范围：
1. 覆盖 OpenAI、DeepSeek、Custom OpenAI-compatible。
2. Anthropic 保留现有非流式能力，不新增流式输出适配。

要求：
1. Provider 调用统一补充诊断阶段，例如 PROVIDER_SELECTED、REQUEST_VALIDATED、HTTP_REQUEST_START、HTTP_RESPONSE_HEADERS、OUTPUT_EXTRACTED、JSON_PARSE_START、JSON_PARSE_FAILED、RESULT_SAVED。
2. 区分 endpoint 错误、API key 缺失或无效、HTTP 4xx/5xx、connect/read timeout、非 JSON、空输出、JSON parse 失败。
3. 所有失败都必须保存 code_quality_review_results.status=FAILED，并写入可读 errorMessage。
4. 前端根据最后 phase 展示卡点提示。
5. 所有 progress detail 和 raw preview 必须脱敏并截断。
6. 补 pytest/respx 测试，覆盖 OpenAI-compatible HTTP 失败、非 JSON、超时、API key 脱敏；OpenAI 至少覆盖一个失败诊断样本。
7. 使用 .\scripts\run-backend-python.cmd test 和 .\scripts\run-frontend.cmd build 验证。

完成后说明：改了什么、为什么、如何验证、剩余风险、下一阶段建议。
完成后停止，等待我验证并确认“继续下一阶段”后再推进。
```

### 16.3 阶段 3：OpenAI-compatible Token Stream

```text
请按 docs/20-ai-review-streaming-diagnostics-plan.md 落地阶段 3：OpenAI-compatible token stream。

前置条件：
1. 阶段 1 Progress SSE 已完成。
2. 阶段 2 Provider 诊断事件标准化已完成。

Provider 范围：
1. 优先 DeepSeek。
2. 同时为 Custom OpenAI-compatible 预留能力，但 Custom 必须通过配置开关显式启用 streaming。
3. 不做 Anthropic token streaming。
4. 不做 OpenAI Responses streaming；OpenAI 放到阶段 4。

要求：
1. 为 OpenAI-compatible Chat Completions 增加 stream=true 调用路径。
2. 解析 SSE data: {...} 和 data: [DONE]，提取 choices[].delta.content。
3. 通过阶段 1 的 SSE 连接向前端推送 delta event。
4. 拼接完整输出后走现有 JSON parse 和 code_quality_review_results 保存。
5. 支持 first byte timeout、idle timeout、total timeout，失败时落库 FAILED。
6. 如果模型不支持 response_format，要有清晰失败或按配置 fallback，不要静默吞掉。
7. 补 respx/mock streaming 测试，覆盖成功、非 JSON、流中断、idle timeout、脱敏。
8. 使用 .\scripts\run-backend-python.cmd test 和 .\scripts\run-frontend.cmd build 验证。

完成后说明：改了什么、为什么、如何验证、剩余风险、下一阶段建议。
完成后停止，等待我验证并确认“继续下一阶段”后再推进。
```

### 16.4 阶段 4：OpenAI Responses Streaming

```text
请按 docs/20-ai-review-streaming-diagnostics-plan.md 落地阶段 4：OpenAI Responses streaming。

前置条件：
1. 阶段 1 Progress SSE 已完成。
2. 阶段 2 Provider 诊断事件标准化已完成。
3. 阶段 3 OpenAI-compatible token stream 已完成或已明确暂缓。

Provider 范围：
1. 只做 OpenAI Responses API。
2. 不做 Anthropic token streaming。

要求：
1. 为 OpenAI Responses Provider 增加 streaming 分支。
2. 解析 OpenAI Responses streaming 的 text delta、completed、failed/error 事件。
3. 如果 strict structured outputs 与 streaming 在当前模型或网关下不可用，必须清晰失败或回退非流式，并在 progress 中说明原因。
4. 通过 SSE 推送 delta event。
5. 拼接完整 output text 后走统一 JSON parse 和结果保存。
6. 补 mock streaming 测试，覆盖成功、Provider error、非 JSON、脱敏。
7. 使用 .\scripts\run-backend-python.cmd test 和 .\scripts\run-frontend.cmd build 验证。

完成后说明：改了什么、为什么、如何验证、剩余风险、下一阶段建议。
完成后停止，等待我验证并确认“继续下一阶段”后再推进。
```

### 16.5 阶段 5：配置化与运维收口

```text
请按 docs/20-ai-review-streaming-diagnostics-plan.md 落地阶段 5：配置化与运维收口。

前置条件：
1. Progress SSE 已完成。
2. 至少 DeepSeek 或 Custom OpenAI-compatible 的 token streaming 已完成，或已明确只启用 Progress SSE。

要求：
1. 增加 Provider capability 配置或等效内置配置，表达 supportsStreaming、supportsResponseFormat、streamingProtocol、timeout 等能力。
2. 前端 Provider 设置页展示 Provider 是否支持 streaming / response_format。
3. Custom Provider 的 streaming 默认关闭，需要用户显式启用。
4. Anthropic 展示为非流式可用、流式暂缓，不能误导为已支持 token streaming。
5. README 补充流式诊断使用方式和排障步骤。
6. docs/10-local-dev-pitfalls.md 补充流式常见坑、超时定位方式、Provider 协议不兼容处理方式。
7. 使用 .\scripts\run-backend-python.cmd test 和 .\scripts\run-frontend.cmd build 验证。

完成后说明：改了什么、为什么、如何验证、剩余风险、后续是否需要单独规划 Anthropic streaming。
完成后停止，等待我验证。
```

## 17. 总控 Prompt：按阶段自主推进

如果希望 Agent 尽量自主推进，可以使用下面的总控 prompt。它允许 Agent 按第 16 节阶段顺序推进，但每个阶段完成后必须停止、汇报验证结果并等待确认，避免范围过大或方向偏移。

```text
请阅读 docs/20-ai-review-streaming-diagnostics-plan.md，然后按文档第 16 节的阶段 prompt 顺序推进 AI Review 流式诊断改造。

授权范围：
1. 可以在当前仓库内新增和修改 backend-python/、frontend/、docs/、README.md 中与当前阶段相关的文件。
2. 可以为当前阶段补充测试、示例和文档。
3. 可以自主运行本地非破坏性验证命令。
4. 每个阶段必须先说明本阶段目标和不做事项，再实施，再验证，再总结。

Provider 范围：
1. 本轮重点是 OpenAI、DeepSeek、Custom OpenAI-compatible。
2. Anthropic 暂时不做 token streaming；现有非流式能力不能被破坏。
3. 阶段 1 Progress SSE 对所有 Provider 通用。

硬性边界：
1. 不要删除、移动或改名现有 Java backend/。
2. 不要切换生产部署入口，不修改真实 webhook 配置。
3. 不要把 API Key、GitLab token、DingTalk webhook 写入代码、日志、测试快照或文档。
4. 遇到需要真实模型、真实 GitLab、钉钉、Docker 网络下载、数据库密码或生产配置的步骤，先使用 mock 或本地配置；无法继续时停下来说明需要什么。
5. 每个阶段结束后必须给出：改了什么、为什么、如何验证、剩余风险、是否建议进入下一阶段。
6. 每个阶段完成后必须停止，等待我验证并确认“继续下一阶段”后再推进。

推进顺序：
1. 阶段 1：Progress SSE 只读流。
2. 阶段 2：Provider 诊断事件标准化。
3. 阶段 3：OpenAI-compatible token stream，优先 DeepSeek / Custom。
4. 阶段 4：OpenAI Responses streaming。
5. 阶段 5：配置化与运维收口。

先从阶段 1 开始。不要跳阶段。每完成一个阶段后停止，汇报验证结果、剩余风险和下一阶段建议，等待我确认后再继续。
```

## 18. Definition of Done

阶段 1 完成标准：

- SSE endpoint 可实时返回 progress。
- 前端 AI Review tab 能实时更新执行过程。
- EventSource 失败时能回退轮询。
- 后台 AI Review 不受 SSE 断连影响。
- Python 后端测试通过。
- 前端构建通过。

全量方案完成标准：

- Progress SSE 可用于所有 Provider。
- DeepSeek / Custom 至少一个 OpenAI-compatible Provider 支持 token streaming。
- OpenAI 是否启用 streaming 有明确配置和文档。
- Anthropic 明确标注为本轮暂缓 token streaming，现有非流式能力不被破坏。
- 所有 Provider 失败都能定位到明确 phase。
- 所有敏感字段脱敏。
- README 和避坑文档包含流式诊断使用方式。
