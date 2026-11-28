# Finding 事实复核推进方案

2026-11-28。本方案承接 [71 号审查引擎路线](71-review-engine-improvement-plan.md) 的第三方向。待 [73 号分组审查](73-agent-review-grouped-execution-rollout-plan.md) 验收并合入 `main` 后，先做 A3A 离线对照，再做 A3B 组内自动复核。73 已合入 `main`（`d77b02c`），验收状态按实际记录确认。

## 1. 首版交付与结果可见时点

事实复核判断原 Finding 的核心主张是否被同一次审查的代码证据明确反驳。首版将裁决和反证附在原 Finding 上，供人工判读。正式 Finding、严重度、行号、反馈和修复引用继续沿用原结果。范围限 73 的分组 Agent Review，定向补证仍沿用现有入口和语义。

每个组在自己的槽位内执行 **首遍审查并校验 Finding → 复核本遍新增 Finding → 判断是否加审 → 如有次审，复核次审新增 Finding → 出组**。等待本遍复核结束或跳过期间，其他组可以继续审查或复核。早先遍次的 Finding 继续按 73 的规则传给下一遍，后续遍次的复核只处理该遍去重后的新增项。各组完成后整任务汇总一份正式 Review Card。「执行过程」在每遍主审提交校验通过后展示待复核 Finding，复核请求返回后批量更新裁决状态。取证中逐条提交候选仍由 71 的 C2 承接。 [73 实时进度](73-agent-review-grouped-execution-rollout-plan.md#8-组内审查实时进度) · [71 后续阶段](71-review-engine-improvement-plan.md#4-后续--审查执行与结果处理)

## 2. 复核输入与裁决契约

- 输入为该遍通过现有校验的新增 Finding 和同次审查的冻结 diff。每个请求用稳定 ID 对齐候选与响应。A3A 固定 Base/Head、原结果、diff、复核模型、Prompt 版本及预算，人工标签仅用于评估。
- 模型裁决如下。执行状态单独记录成功、跳过或失败及原因。

  | 裁决 | 含义 |
  |---|---|
  | `KEEP` | 在可核对的材料中未发现明确反证。 |
  | `CONTRADICTED` | 代码里有可定位的事实，直接推翻该 Finding 的核心主张。 |
  | `NEEDS_CONTEXT` | 材料不足，需要更多上下文才能裁决。 |

- `CONTRADICTED` 必须给出简短理由、仓库相对路径、`OLD` 或 `NEW` 侧及起止行。程序核对路径、侧、行区间均存在于实际提供给复核器的 diff。若带短引文，同时验证引文与对应侧的原文匹配。程序验证出处，模型提出事实判断，人工标注样本衡量事实判断是否成立。
- 未知 ID、重复裁决、缺少裁决、无效引用、超时和预算不足记录相应原因。可确认归属的有效裁决随原结果保留。证据原文留在执行和已授权评估范围内。正式结果附加信息保存简短理由、坐标和状态。
- 明确反证示例是同一执行路径中，访问列表第一项前已有空列表提前返回。只有其他分支存在类似检查，或冻结 diff 缺少相关调用链时，按需要更多上下文处理。

## 3. A3A 反证复核对照

- **改动量等级为中。** 涉及复核提示、Provider 调用、引用校验及现有评估记录的复用，正式审查入口和页面维持原流程。
- **目标与范围。** 复用固定提交回放、`EvaluationCase` 和 `EvaluationRun`，为同一批原 Finding 记录模型裁决、人工结论、反证坐标、耗时、用量和失败原因。优先抽取高严重度、高置信度且证据不足的候选，同时覆盖已确认的真问题、明确误报和上下文缺失。存在风险信号的零 Finding 任务可单独抽样用于漏报分析。
- **非目标。** 正式发布、通知、自动修复、项目记忆和自动过滤留待各自流程处理。
- **验收。** 用固定标注样本逐条对照原 Finding、diff 和裁决，报告正确识别的误报数、可裁决误报总数、错否真问题数、真问题总数及高严重度分层。记录证据不足、超时、无效引用的数量，以及额外耗时和 Token。对复核判为有反证的高严重度问题逐条人工复查。用合成数据验证引文错侧、行号越界、未知 ID 和异常回退，评估报告区分真实模型样本与替身验证。
- **授权边界与停止点。** 本地固定样本或已授权的隔离环境内执行。真实项目材料只在已有授权范围内使用。交付可追溯到原 diff 的逐条结果和汇总记录，注明样本缺口。A3B 使用同一裁决契约，线上启用时机由用户安排。 [现有评估记录](../backend-python/app/evaluation/models.py)

## 4. A3B 组内自动复核

A3B 整体改动量等级为大，涉及 Worker、Backend 完成回传和结果读端。先完成兼容回传并通过结果 API 验收，再接现有任务详情。两步均保留正式终态结果链路。

### A3B1 Worker 和结果回传

- **改动量等级为大。** 组内执行、Worker 完成请求和结果附加字段需要联动校验。
- **目标与范围。** 从 73 每遍完成并去重后的新增 Finding 接入 A3A。复用当前任务的 Runtime、协议和模型，发起独立复核请求。复核使用所在组的冻结 diff，受 Runtime 的内联 diff 预算约束。复核时长计入所在组，实际 Token 计入任务。预算不足时跳过。复核结束或跳过后，按 73 的现有预算和新增 Finding 规则判断是否再审。73 回退至整任务单遍时沿用原执行路径。
- **回传契约。** 通过可选完成字段传回复核附加结果，包含最终卡片 Finding 序号、组、遍次、裁决或执行状态，以及可选理由和校验后的引用坐标。Worker 在最终去重和汇总后建立关联，Backend 核对领取代次、序号越界、重复关联及字段有效性，再随对应结果保存。旧 Worker 可以省略该字段，旧结果可以直接读取。重新领取沿用整任务重跑。
- **非目标。** 自动隐藏、降级、跨组仲裁、后续遍次撤销早先 Finding，以及按组发布正式结果。
- **验收。** 替身验证两个组可同时推进，首遍与次审各自只发送当遍增量。覆盖零新增、模型超时、预算触顶、错引用、结果去重、旧 Worker 和旧结果。验证同一个正常 Review 任务最终只保存一份 Review Card，复核失败时原 Finding 仍可查询。
- **授权边界与停止点。** 在本地或隔离运行验证 Worker 完成回传和现有结果接口。通过后可停在兼容的后端结果，页面展示可以独立验收。回退前按 73 处理在途分组任务，历史正式 Finding 沿用现有读端。

### A3B2 Finding 详情展示

- **改动量等级为小。** 局限于现有 Finding 详情，复用 A3B1 的结果字段。
- **目标与范围。** 在「任务详情 → 审查结果 → 展开 Finding → 上下文与判断依据」增加「事实复核」区块。显示裁决、理由及反证路径和行区间。跳过或失败时显示原因。只有存在复核记录的 Finding 显示区块。
- **非目标。** 新页面、组内即时发布、异步候选显示及对外通知。
- **验收。** 从正常 MR 或手动审查入口运行满足 73 分组条件的固定样本。在「执行过程」确认组完成，在最终 Review Card 打开 Finding，将裁决及反证位置与同次 diff 对照。再核对一条有跳过或失败记录的结果和一条历史结果。记录浏览器验收及前端 build。
- **授权边界与停止点。** 本地或隔离环境完成验收并记录步骤。生产验证由用户安排。首版裁决仅用于人工判读，自动过滤另根据真实标注样本的误伤结果决定。

## 5. 与 Open Code Review 的差异

| 行为 | OCR `d4f568f` | 平台首版 |
|---|---|---|
| 复核时机 | 每组每遍结束后收齐异步评论定位，复核本遍新增评论。 | 同组每遍校验后复核新增 Finding，使用本次冻结 diff。 |
| 跨遍结果 | 本遍过滤后留下的评论传给下一遍查遗漏。下一遍复核限于当遍新增，早先评论留在累积结果。 | 复核裁决随 Finding 记录。73 的跨遍传递和去重继续生效，已有 Finding 留在正式结果。 |
| 裁决用途 | 删除被复核判错的新增评论。 | 附上裁决和证据，供人工核对。 |
| 用户可见时点 | CLI 整次审查后输出，Viewer 在组结果落盘后可刷新查看，GitLab CI 示例在取得最终 JSON 后发布。 | 组状态通过执行进度展示，Finding 和裁决随任务终态一次返回。 |

[OCR 逐遍复核](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/agent/agent.go#L1585) · [OCR 复核候选范围](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/agent/agent.go#L1872) · [OCR 结果过滤](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/agent/agent.go#L1978) · [OCR 组结果写入](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/agent/agent.go#L831) · [OCR CLI 出结果](https://github.com/alibaba/open-code-review/blob/d4f568f/cmd/opencodereview/review_cmd.go#L318) · [GitLab CI 示例](https://github.com/alibaba/open-code-review/blob/d4f568f/examples/gitlab_ci/.gitlab-ci.yml#L127)

## 6. 复验步骤与实现记录

### A3A 固定样本

在本地或已授权的隔离数据库准备带 Finding 快照的评估样本，至少各选一条已确认误报、真实问题和缺上下文样本。在同一数据库的「模型连接与 Review 配置」选择启用的 Chat Completions 或 Responses Runtime。离线入口使用该 Runtime、当前执行预算以及后端数据库和凭据加密配置。

准备 UTF-8 JSON 文件，顶层为数组，每项含真实评估样本编号`caseId`、固定提交`base`和`head`、同次审查的`diff`。从仓库根目录运行以下 PowerShell，使用后端 Python 3.12+ 环境。评估模块直接执行，启动脚本目前没有离线评估子命令。

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'backend-python')
& .\backend-python\.venv\Scripts\python.exe -B -m app.evaluation.fact_check .\samples.json
```

用输出中的`evaluationRunId`查看评估记录。逐条到固定 diff 核对反证是否成立，重点检查`incorrectlyContradicted`及其高严重度分层。`decidableFalsePositives`只计模型给出`KEEP`或`CONTRADICTED`的人工误报样本，`outcomes`单列需补上下文、跳过和失败原因。输出可单独保存用于对照，评估记录保留提交、diff 哈希和裁决坐标。

### A3B 正常入口

1. 启动本工作树的 Backend、Agent Worker 和前端，确认模型连接为 Chat Completions 或 Responses，兼容 Worker 在线。回传字段可选，数据库沿用现有 Finding JSON。分开更新时先升级 Backend，再升级 Worker 和前端。
2. 用普通 MR 或手动审查触发能生成 Finding 的任务。新版 73 自动分组，单文件也按单组复核。首审、复核和加审共用组期限。任务运行中，在「执行过程 → 审查组」展开组，核对本遍提交后候选进入待复核，以及该批裁决更新。等任务终态，在唯一一份正式 Review Card 展开 Finding 的「上下文与判断依据」，核对「事实复核」的裁决、理由，以及命中反证时的文件、diff 侧和行区间。 [73 组内实时进度](73-agent-review-grouped-execution-rollout-plan.md#8-组内审查实时进度)
3. 查一份旧任务以及一份复核失败或跳过的任务。确认旧任务按原样读取，复核失败时原 Finding 仍在。可用以下替身命令复现超时和无效坐标，并验证同组第二遍开始前已处理第一遍复核。

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'backend-python')
& .\backend-python\.venv\Scripts\python.exe -B -m app.agent_review_spike.synthetic_grouped_validation
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-frontend.ps1 build
```

### 本地验收记录

- Chat Completions 替身覆盖 9 个组、峰值 8 并发、跨遍去重、7 条首遍复核和 2 条复核失败后的结果保留。Responses 替身覆盖两遍审查各自的新增复核、Token 合计、错侧引文、未知 ID 和离线标注对照的落库。另核对了 Token 软上限触发后跳过复核并保留原 Finding。
- 隔离 SQLite 使用实际 Worker 完成接口和任务结果接口核对了裁决回传、旧 Worker 省略复核字段、重复关联、请求重试和单份 Review Card。前端生产构建通过。
- 真实 Provider 的复核准确率、生产数据库和真实浏览器任务详情待按上述步骤验收。未运行单元测试。
