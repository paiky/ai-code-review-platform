# Agent Review 分组并发开发推进方案

2026-11-28。本方案承接 [71 号审查引擎路线](71-review-engine-improvement-plan.md) 的第二个方向。以 Open Code Review `d4f568f` 的分组、并发槽位和组内多遍为基准。推进顺序为 B2A 离线分组验证、B2B 单遍并发、B3 组内多遍。各阶段在同一开发分支连续推进，通过本地验收后进入下一阶段。生产接入排在 [72 号文件规则首版](72-file-rule-matching-rollout-plan.md) 验收之后，由用户安排。

## 1. 交付效果与范围

同一次 Agent Review 中，相关变更归入同一个组，多个组可同时审查。每组看到本组 diff、适用的文件规则和组外变更摘要，可以按需补读组外证据。现有 Python Worker 在单个 Job 内使用有界线程池。一个组作为一个执行单元，拿到槽位后在槽位内依次完成适用的审查遍次与后处理，组结束即释放槽位。任务在现有「执行过程」显示组进度，全部必审组完成后汇总为一份正式 Review Card，Finding 继续使用现有结果区展示。

本方向限于 Agent Review 的执行编排。重新执行时按整任务重跑，适用的 Standard 降级也从完整审查范围重新执行。完成组续跑和跨引擎结果复用归入 [71 的后续优化事项](71-review-engine-improvement-plan.md#7-后续优化事项)。组内事实复核由 [A3B](71-review-engine-improvement-plan.md#a3b--主审查接入组内事实复核) 独立交付。候选评论异步定位和增量发布沿用各自阶段。

## 2. 分组、取证与执行契约

### 2.1 分组与文件规则

1. 以上游默认语义分组为基准。Worker 使用已纳入审查的文件路径、变更状态和增删行数，达到 4 个文件时调用本次 Runtime 的模型为相关文件分组。单文件直接审查。2–3 个文件且总增删少于 200 行时合为一组，否则逐文件分组。B2A 用固定样本验证 Mapper 与 DAO、接口与实现等关系的同组效果，以及被拆开时的组外取证效果。
2. 程序校验模型返回，忽略未知及重复索引，遗漏文件补为单文件组，分组调用失败时逐文件审查。每组最多 10 个文件，超组上下文预算时拆分。每个纳入文件恰好归一个组，记录本领取代次的稳定组序、`groupId`、组内路径和分组方式。组数由变更内容和分组结果决定，超过并发槽位的组进入同一个待审队列。 [OCR 分组与回退](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/agent/grouping.go#L68) · [OCR 默认阈值](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/config/template/task_template.json#L43)
3. 兼容分组的 Job 输入留存独立的基础指令（含 Profile 和项目策略）及 72 的规则目录版本。Worker 拿到组计划后，复用 72 的规则构建器，按本组路径和安全 diff 渲染组指令，使用与入队时一致的规则目录。目录不一致时回到原整任务输入。`OrderMapper.xml` 和对应 DAO 可以同组并各用自己的规则，同一规则正文仍在组内去重。公开进度摘要仅用于展示。

### 2.2 组外取证与 Finding 归属

每组请求内联本组 diff，附上有界的组外变更清单，列出路径、变更状态和可取得的增删行数。清单裁剪时标明省略数量。组外文件正文由 Agent 用现有工具按需读取，各组共享同一任务的冻结材料和只读 worktree。组间无需交换对话，也无需等另一组完成。例如 Mapper 被拆到另一组，审查 Java 变更的组仍可读取 Mapper diff 来核对参数。跨组关系是否被模型识别和追查，由 B2A 用样本核验。

当前 `ReviewToolExecutor` 用同一份 `changed_files` 校验 `read_diff_range` 和 `submit_review`。分组执行需要向 Runner 提供本组审查路径与任务级可取证 diff 两个范围。`read_diff_range` 可读本任务原有授权范围内的其他组 diff，路径、行数和字节限制沿用现有工具。`submit_review` 用本组路径验证 Finding 归属，证据可引用经过现有校验的组外代码。无分组输入时沿用当前统一范围。 [Runner 构建取证输入](../backend-python/app/agent_review_spike/chat_completions_runner.py#L198) · [工具校验](../backend-python/app/agent_review_spike/tool_executor.py#L283)

### 2.3 按组调度

Backend 通过现有 Agent Job 输入下发审查范围、分组执行配置和构建组指令所需的材料。兼容 Worker 领取后先生成并记录本次组计划，再派发组任务。旧任务、未覆盖的 Runtime 或入队时没有兼容 Worker 的新任务走整任务路径。需要重领时，新领取代次从该 Job 输入重新分组并运行全部必审组。若进入 Standard 降级，Standard 使用 72 已保存的整任务输入重新审查全部纳入文件。本次执行结果仅由当前领取代次汇总。

在 `worker.py::_run_job` 内按组派发，默认 **8 个并发槽位**，单个 Job 实际同时运行的组数取待审组数与并发槽位数的较小值。每组独立持有审查对话、取证计数和进度缓冲，共用任务的 Runtime 和取消信号。队列按本次组序派发，空出的槽位可立即启动下一待审组。组执行计时从拿到槽位开始。取消时停止派发并让运行组收敛，再走现有取消终态。进度通过现有心跳上报，按 `claimAttempt`、`groupId` 和遍次关联。 [Worker 执行与终态](../backend-python/app/agent_review/worker.py#L261) · [OCR 并发槽位](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/agent/agent.go#L688)

### 2.4 组内审查顺序

1. **首审。** B2B 在槽位内用一条独立对话完成本组首遍审查。校验 Review Card，记录本遍有效 Finding。B2B 只有首遍，完成后即可释放槽位。
2. **首遍事实复核。** A3B 接入后，Worker 在同一槽位对本遍新增 Finding 发起一次独立模型调用。有候选且预算允许时执行，裁决作为附加结果记录，正式 Finding 沿用当前结果语义。
3. **同组加审。** B3 启用后，每组按自己的上一遍结果和 `effort` 判断是否继续。上一遍有新增有效 Finding 且额度允许时，在原槽位开新对话，带上本组 diff、规则和此前经校验并保留的 Finding 继续查遗漏。多个组可以同时进入后续遍次。
4. **逐遍复核与出组。** A3B 接入后，每遍结束都用同样方式复核本遍新增 Finding，复核结束或跳过后再决定下一遍。达到遍次上限、当前遍没有新增有效 Finding、额度不足或组超时即结束本组并释放槽位。A3B 接入前，模型输出校验直接衔接下一步。候选评论异步定位和展示沿 71 的后续阶段安排。

### 2.5 预算与正式结果

| 控制项 | 分组任务的默认口径 |
|---|---|
| 并发 `concurrency` | 每个 Job 默认 8 个组槽位，可随执行配置调整。组数可以超过槽位数。 |
| 每组遍次 `effort` | B2B 单遍验收。B3 接入后，`low`、`medium`、`high` 每组最多 1、2、3 遍，默认 `medium`。符合条件的各组分别继续。 |
| 轮次和取证 | 按组内每遍配置轮次、工具调用、取证、源码字节及提交阈值。单 Runner 的 `18／15` 上限退出分组 Job 的合计预算口径。B1 实测各遍所需额度。 |
| 时间 | 组内计时覆盖审查各遍和复核，上游基线为每组 15 分钟乘该组允许遍数。单请求超时和 Provider 限流独立处理。 |
| 整任务 Token | 可选软上限，默认关闭。配置后累计分组决策、各遍审查和复核用量。触及上限时停止派发后续组与遍次，运行中的遍次收敛。 |

组并发、每组审几遍和任务成本各自控制。验收记录实际峰值并发、Token、时长、限流和收敛结果。旧单 Runner 任务继续按现有 Runtime 参数执行。 [OCR 并发、超时、Token 和 effort](https://github.com/alibaba/open-code-review/blob/d4f568f/pages/src/content/docs/zh/cli-reference.md#L122) · [B1 预算对照](71-review-engine-improvement-plan.md#b1--预算对照)

组提交先经现有 Review Card 校验，汇总按稳定组序去重，沿用现有严重度和卡片上限。Worker 在原 `/complete` 请求附上当次各必审组的路径和完成状态。Backend 校验当前领取代次，以及成功首审组的路径能否完整且无重复地覆盖 Job 的纳入文件，再走现有完成与通知链路。必审组失败、缺组或合并卡片超限时，记录原因并走现有失败或适用的降级。零 Finding 的成功组计为已覆盖。

## 3. 开发推进与停止点

### B2A · 离线分组与并发验证

- **改动量等级：中。** 涉及变更关系识别、Runner 输入切片、取证范围和离线对照。
- **目标与范围**　用固定 Base/Head、模型和规则目录版本验证 OCR 式语义分组及证据范围。首个接入对象为 OpenAI Chat Completions Runner。用替身传输验证 8 个槽位及超过槽位后的排队。串并行使用同一份组计划、模型和组预算。质量对照使用固定提交及相同的对照预算，记录与整任务审查的召回及成本差异。
- **历史设计与页面**　复用现有 diff 解析、Runner 和固定提交回放。验收输出组成员、分组原因、组起止时间、取证和 Finding；任务页面无需接入。
- **非目标**　接入正式 Worker 队列或保存检查点。
- **验收**　覆盖分组阈值、模型失败或返回重复与遗漏文件、组超限、Mapper 与 DAO 同组及跨组依赖。检查每个文件恰好归一组、规则按路径绑定、组外 diff 可取证、组外 Finding 被拒绝。替身验证 8 组请求重叠，第 9 组等槽位释放后启动。记录组覆盖、重复率、Token、耗时和 Provider 错误。有人工标注时比较高风险召回，缺标注时记为未评估。
- **授权边界与停止点**　只在本地固定样本或已授权的隔离环境运行。交付可复现的分组与并发对照后进入 B2B。

### B2B · 多组并发单遍接入

- **改动量等级：大。** 局部重构单 Job 执行层，同时涉及 Backend 兼容领取、Worker 调度、结果覆盖校验和执行过程展示。覆盖校验与调度一起交付。
- **目标与范围**　接入正常 Agent Review 入口，首个接入对象为已在 B2A 验证的 OpenAI Chat Completions Runner。按默认 8 个槽位运行各组首遍，超过槽位数时排队。Worker 中断后按 A4 既有租约机制重领并从 Job 输入完整重跑。
- **历史设计与页面**　复用现有任务入口、Runtime 选择、租约和幂等完成。任务详情「执行过程」增加组标识、文件数、状态和结束原因，正式结果仍进入现有结果区。进度接口的新增字段可选，旧任务仍可读取。
- **非目标**　组级持久化、组级自动重试、第二遍或调整 Worker 池的任务并发。
- **验收**　从正常入口确认默认槽位运行、超过槽位排队、全量覆盖、单份正式卡片、一次通知和旧数据可读。覆盖旧 Worker、混合版本、限流、取消和 Worker 中断。接管时核对整任务重跑及领取代次校验。若触发 Standard 降级，核对 Standard 从完整输入执行。对同一组计划比较串并行耗时和错误率。Backend 先部署兼容读写，分组任务交给支持分组的 Worker。
- **授权边界与停止点**　本地或隔离验证通过后，记录单遍接入结果，再继续 B3。生产验证由用户安排。回退先处理在途分组任务，再回退应用版本。

### B3 · 同组多遍查遗漏

- **改动量等级：中。** 复用 B2B 分组执行，在当前领取代次内增加逐组 `effort` 上限、提前结束、后续遍次 Prompt 和结果归并。
- **目标与范围**　按 `effort` 控制各组最多运行 1、2 或 3 遍，默认最多 2 遍。有新增有效 Finding 且组内额度允许的组立即在自己的槽位开始下一遍。
- **历史设计与页面**　组进度增加遍次、用量、结束原因和新增 Finding 数。重复问题保留最早有效遍次的位置及标识。同一领取代次内，后续遍失败且首遍完整时，保留此前成功遍次的结果并标记加审未完成。Worker 中断并被接管时，整任务重新分组和审查。用户取消按既有取消终态处理。
- **非目标**　固定遍次全量执行、跨组汇总后再选组加审、将查遗漏与 A3B 复核合为一次模型调用。
- **验收**　用替身证明一组加审时另一组仍可首审，至少两组可以同时加审，活跃组数受槽位数约束。核对三个 `effort` 档、下一遍只携带本组已有 Finding、零新增提前结束、跨遍去重和单份终态。验证显式 Token 上限、超时和 Worker 接管全量重跑。以相同输入、模型和对照预算比较单遍与多遍，有标注时核对新增真阳性、高风险召回和成本。
- **授权边界与停止点**　隔离验收通过后独立交付。缺少标注时先交付可复现行为和成本记录，召回收益待生产样本确认。生产验证由用户安排。

## 4. 配置与本地验收

从 72 已合入的 `main` 开发，首版先验证 Chat Completions，B3 补充接入 Responses。「模型连接与 Review 配置 → Agent 执行预算」保存的分组设置用于新任务。Backend 见到支持分组的 Worker 后将设置写入 Job，重领沿用原值。没有已保存的设置时，Docker Compose 透传的以下变量用于部署默认值。

| Backend 环境变量 | 默认 | 取值 |
|---|---|---|
| `AGENT_REVIEW_GROUP_CONCURRENCY` | `8` | 正整数 |
| `AGENT_REVIEW_GROUP_EFFORT` | `medium` | `low`、`medium`、`high`，对应每组最多 1、2、3 遍 |
| `AGENT_REVIEW_GROUP_MAX_TOKENS` | `0` | 非负整数，0 表示关闭整任务软上限 |

Worker 在每遍结束后汇总 Provider 返回的 Token。已启动的一遍可以收敛，未启动的组或遍次在额度耗尽后跳过。若因此缺少必审组，按失败或现有 Standard 降级处理。组进度显示当前状态、问题数和累计用量。现有单遍 Runtime 超时和组剩余时间共同约束每遍请求。超出 250 组时标记省略的进度条目，覆盖校验仍使用全部组。

在 PowerShell 从仓库根目录运行以下替身 Provider 验收。使用已安装项目依赖的 Python 环境，命令仅使用本地合成变更。

```powershell
$env:PYTHONPATH = Join-Path $PWD 'backend-python'
& .\backend-python\.venv\Scripts\python.exe -B -m app.agent_review_spike.synthetic_grouped_validation
```

正常入口验收时，使用支持 Chat Completions 或 Responses 的 Agent Runtime 和支持分组的 Worker。选包含多个独立模块的 MR 或手动审查，展开任务详情的「执行过程」核对组数、排队、遍次、问题数和结束原因。最后检查现有结果区只产生一份正式 Review Card。关闭分组后重新发起任务，核对原整任务视图。

### B3 补充 · Responses 与分组设置

- **改动量等级：大。** 涉及 Agent 设置接口、存储、两种 HTTP Runner、Worker 领取与设置页。
- **目标与范围**　分组和各遍审查沿用任务选定的 Chat Completions 或 Responses Runtime。设置页用数字输入和开关管理分组启用、并发、最大遍数、单遍模型轮数、整任务 Token 软上限和组时间上限。默认单遍最多 100 轮，最迟提交回合从轮数减 3；单遍原有取证、工具和超时预算继续生效。
- **契约**　沿用 Agent 设置 GET/PUT。新增 `groupedReview`，字段为 `enabled`、`concurrency`、`maxPasses`、`maxTurns`、`maxTokens` 和 `timeoutMinutesPerPass`。后两项用 0 表示关闭，默认分别为 0 和 15。默认启用分组，并发 8、最多 2 遍。保存设置影响新任务，已有部署环境变量作为首次配置及恢复默认值的来源。
- **非目标**　新增其他协议的分组执行、接入 A3B 事实复核或改变历史整任务的预算。
- **验收**　用替身验证 Responses 分组、跨组 diff 读取与组内 Finding、次审结果汇总、设定预算以及旧 Worker 继续领取原整任务。构建前端和 Worker 镜像。
- **授权边界与停止点**　本地验收后交付。生产按既有发布流程验证，回退前收敛已入队的新版分组任务。

### 本地推进结果

B2A、B2B、B3 已在 `feat/review-grouped-execution` 连续实现。开发基线为包含 72 的 `main` 提交 `a790665`。

| 阶段 | 本地验收 |
|---|---|
| B2A | 10 个合成变更文件分成 9 组，观察到并发峰值为 8。串行与并发正式卡片一致。验证规则按组渲染、组外 diff 可读、组外 Finding 被拒绝，以及异常分组回退。 |
| B2B | 用临时 SQLite、Worker API 和替身模型走通入队、领取、心跳、组进度与落库。验证旧 Worker 无法领取、接管重新执行、缺组与旧代次被拒绝、取消优先于迟到完成。重复完成及迟到失败保留同一正式结果，汇总通知入口只调用一次。验证降级传给 Standard 的是整任务 diff 与规则输入。 |
| B3 | 替身验证至少两组同时进入次审。默认档有 7 组运行第二遍，高档有 7 组运行第三遍；检查只传本组已有 Finding、去重、零新增提前结束和 Token 软上限停止派发。前端构建和任务进度解析验证通过。 |
| B3 补充 | Responses 替身通过 Worker 分发、8 槽并发、跨组取证、组外 Finding 拒绝、次审及 Token 软上限验证，生效预算为 100 轮和第 97 轮提交。隔离 SQLite 核对 V69、设置保存和恢复默认、新旧 Worker 领取范围。前端与 Worker 镜像构建通过。 |

生产 Provider 的并发限流、真实 MySQL、通知送达和有标注样本的召回比较待生产验收。A3B 继续按 71 独立推进。未运行单元测试。

## 5. 参考实现

Open Code Review `d4f568f` 为每组分配一个并发槽位，在槽位内逐遍审查，并对每遍新增评论做事实复核。下一遍用同组材料和已保留评论构建新对话，本遍无新增结果时结束该组。事实复核由 A3B 独立接入平台的每遍结果处理。 [OCR 组调度](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/agent/agent.go#L736) · [OCR 多遍与复核顺序](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/agent/agent.go#L1530) · [OCR 组外取证](https://github.com/alibaba/open-code-review/blob/d4f568f/pages/src/content/docs/zh/tools.md#各阶段工具可用性)
