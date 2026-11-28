# 文件规则匹配首版落地与验收计划

2026-11-28。本文承接 [审查引擎优化与运营指标推进方案](71-review-engine-improvement-plan.md)，单独落地 Open Code Review 的文件规则匹配思路。首版让新项目可以直接进入 Review，按每个变更文件选择语言、模板、配置或依赖规则。项目端类型保留为可选项目级上下文。

## 1. 目标与结论

首版交付以下行为：

```text
MR / Push / manual review
  -> 保留现有 changed files 和审查范围
  -> 每个已纳入文件解析一份 file rule
  -> file rule blocks + 可选项目端 Prompt + 项目规范 + Context Pack
  -> 发送给 Standard / Agent Provider
```

Open Code Review 的 `system_rules.json` 和 `rule_docs` 作为规则资产来源。首版复制并适配其文件路径、文件名、扩展名和默认回退映射。固定版本有 74 条路径映射和 70 份规则文档，覆盖语言、模板、依赖、配置、IDL、基础设施和特殊文件。

首版不改变文件纳入和排除策略。已有 changed files 继续进入审查，规则匹配只决定 Prompt 检查清单。敏感文件、二进制、测试目录、超大 Diff 和其他文件边界继续沿用平台现有链路。

首版不要求新项目预先配置 `targetType`。已有显式项目端类型继续作为项目级 Prompt 注入。没有显式类型时使用通用项目上下文，文件规则仍然生效。混合项目按文件匹配不同规则，不因自动检测出多个端类型阻断 Review。

## 2. 改动边界

### 2.1 规则资产范围

规则目录保留上游映射和正文的来源版本。以下示例按固定版本的实际映射列出。

| 类别 | 典型文件 | 规则来源 |
|---|---|---|
| Java / Kotlin / Scala | `.java`、`.kt`、`.kts`、`.scala` | 对应语言规则 |
| C 系列 | `.c`、`.cpp`、`.cc`、`.cxx`、`.m`、`.mm`、`.h` | C、C++、Objective-C、MATLAB。`.h` 走通用回退 |
| Web 与脚本 | `.js`、`.jsx`、`.ts`、`.tsx`、`.astro`、`.py`、`.rb`、`.php` | 对应语言或模板规则。`.vue`、`.svelte` 走通用回退 |
| 移动与跨端 | `.swift`、`.kt`、`build.gradle`、`.dart`、`Podfile` | Swift、Kotlin 和 `build.gradle` 专属规则。`.dart`、`Podfile` 与其他未命中规则的 `.gradle` 走通用回退 |
| 数据和模板 | `.sql`、Mapper XML、`.graphql`、`.prisma`、`.proto`、`.json`、`.yaml` | SQL、Mapper、Schema、配置和协议规则 |
| 依赖和构建 | `pom.xml`、`package.json`、`build.gradle`、`Cargo.toml`、`composer.json`、`Gemfile` | 依赖、插件、构建和版本管理规则 |
| 基础设施和策略 | `.tf`、`.hcl`、`.bicep`、`.nix`、`.rego`、GitHub Actions YAML | Terraform、云资源、策略和流水线规则 |
| 通用回退 | 未命中特殊模式的已纳入文件 | `default.md` |

复制上游正文时保留 Apache-2.0 许可证和来源版本。规则正文可以保留英文，平台 Prompt 继续约束 Finding 的中文输出。涉及平台已有数据库、缓存、MQ、项目策略和安全规则时，采用平台规则追加方式，不覆盖现有平台约束。

### 2.2 匹配优先级

解析器按以下顺序返回一个主规则，并保留命中的 Pattern 和来源：

```text
精确文件名
  > 特殊用途路径
  > 扩展名或扩展名集合（仅 .m 允许内容识别覆盖）
  > default.md
```

典型顺序如下：

1. `pom.xml` 先于普通 XML。
2. `**/*mapper*.xml` 和 `**/*dao*.xml` 先于普通 XML。
3. `.github/workflows/*.yml` 先于普通 YAML。
4. `package.json` 先于普通 JSON。`tsconfig.json` 使用上游通用 JSON 规则。
5. 固定版本的 `.m` 路径默认规则为 MATLAB。有限内容片段明确指向 Objective-C 时使用 `objc.md`。内容无法读取时保留 MATLAB，并记录 `CONTENT_SNIFF_UNAVAILABLE`。
6. 未命中时使用 `default.md`，不能因规则解析失败而跳过文件或跳过整次 Review。

规则条目按映射文件的稳定顺序解析，重复规则正文按内容摘要去重。每个文件只产生一份主规则，附加平台项目规则和统一安全规则单独记录。

### 2.3 Prompt 组合

最终请求由以下部分组成：

```text
平台固定 Agent / Standard 指令
  + 可选项目端类型 Prompt
  + 可选项目 Review Policy 与 Memory
  + file rule blocks
  + changed files / diff / Context Pack
```

混合项目按规则正文去重，每份正文前的 `Files` JSON 数组列出适用路径。匹配对路径分隔符和大小写做归一，Prompt 使用实际相对路径。`.m` 仅从已有可信 diff 的新侧首行附近读取最多 4 KiB，可用内容不足时按 MATLAB 规则处理。规则块受 16,000 UTF-8 字节的总量限制，按不同规则分配空间，超限时裁剪路径列表或正文，并记录裁剪状态。Finding 仍归属于已有 changed files。

## 3. 现有架构影响

### 3.1 主要增量位置

| 位置 | 首版改动 |
|---|---|
| `backend-python/app/review_rules/` | 新增规则目录、映射解析、Pattern 优先级、来源摘要和规则版本。 |
| `backend-python/app/agent_review/service.py` | Agent 入队时将规则文本写入现有 `reviewInstructions`，同一领取或降级可复用队列快照。 |
| `backend-python/app/code_quality/service.py` | Standard 使用同一解析器和规则渲染，随现有项目策略和 Prompt 一起送到 Provider。 |
| `backend-python/app/project_integration/` | 新项目使用通用文件规则 Profile，沿用端类型检测、风险模板和通知路由。 |
| `docs/03-api-contract.md` | 记录可省略的 `FILE_RULES_RESOLVED` 进度事件与无端类型项目的接入行为。 |
| `frontend/src` | 在现有「执行过程 → 上下文准备」抽屉显示规则版本、命中、回退、错误和裁剪。 |

### 3.2 历史设计影响

- 新项目可省略 `targetType`。手工创建时存储 `GENERAL`，Webhook 自动接入保留原有主端检测，用于风险提醒、通知和上下文检索。两种接入均可使用 `file-default-ai-review`，由变更文件决定文件级检查清单。旧项目沿用现有类型和 Profile。
- `detected_target_types` 保留为检测事实。多个检测结果不再单独阻断文件规则 Review。项目级 Provider 或 Profile 选择仍遵循已有显式配置。
- `reviewInstructions` 保持原字段和调用方兼容。文件规则追加在统一请求构建处，不能只改某个 Runner 的局部 Prompt。
- `changedFiles`、Finding schema、Review Card、任务状态、通知和结果页面保持原契约。
- 文件规则解析异常记录 `FILE_RULE_RESOLUTION_FAILED`，回退 `default.md` 或现有通用 Prompt。规则缺失不产生成功的空规则状态。

### 3.3 页面影响

任务详情的「执行过程 → 上下文准备」追加规则摘要，沿用当前任务列表、任务详情主布局和 Review 结果卡片。

```text
规则版本：目录 SHA-256 的前 12 位
已匹配：12 个文件
回退 default：2 个文件
规则解析失败：0 个文件
```

逐文件的路径、Pattern、规则键和来源版本可从任务进度 API 查询，返回条目按字节上限裁剪。

## 4. 分阶段实施

### F0 · 改前基线与规则资产清单

- **改动量等级：小。** 复用固定提交回放和现有请求记录，不改业务执行。
- **目标与范围**　从上游 `system_rules.json`、`rule_docs` 和 `supported_file_types.json` 生成平台规则资产清单。记录规则键、Pattern、文件类型、规则正文摘要、许可证来源和适配状态。准备三类固定输入，纯语言文件、特殊用途文件和混合全栈文件。
- **改动性质**　资料和回放增量。
- **历史设计影响**　无。
- **页面变化**　无。
- **验收**　清单可重复生成。至少核对 Java、C、Objective-C、TypeScript、Python、Swift、Dart、SQL、Mapper XML、POM、Gradle、package.json 和 YAML。固定请求保存改前 Prompt 摘要和当前 `targetType` 行为。
- **停止点**　规则来源、许可证、未适配文档和固定样本清单齐全后停止。

#### A0 / F0 验收记录

2026-11-28，已完成 A0 / F0。平台基线为 `main@0b4a2f2`，上游固定为 `d4f568f71d3a9d5c5ec972791b1509e40cd31ad1`。两次离线采样生成了相同的清单和请求摘要。 [F0 规则资产与改前基线](72-file-rule-matching-f0.json)

- 规则清单按上游 JSON 顺序保存 74 条映射及对应文件名，核对 70 份规则正文、映射文件和 Apache-2.0 许可证的 Git blob SHA-256。所有映射均有正文，正文待 F1 导入。上游 144 项文件过滤允许列表随清单留作比对；平台继续使用自己的文件纳入和排除策略。
- 改前基线覆盖纯 Java、纯 TypeScript、多语言、特殊用途文件和全栈混合共五个合成提交，合计 30 个文件。清单保存空基线提交、各样本提交 SHA、文件内容、Diff 摘要及首版预期。复跑时按 `fixtureGit` 的对象格式、作者、时间和提交消息重建两个提交，以 Git 文件名顺序和七位索引摘要生成 Diff，再核对 JSON 中的 SHA 和 UTF-8 字节数。
- 使用当前分支代码及内存 SQLite 调用项目自动接入和端类型解析。自动接入的全栈样本检测到 `WEB_PC`、`BACKEND`，当前主端和 Profile 为 Web。手动预建 Backend 项目仍使用 Backend Profile。另以主端为空的历史项目输入核验歧义判断，混合样本返回多个端类型。新建任务的路由兼容留给 F3。
- 使用 `enqueue_agent_review` 在队列写入前捕获 Agent 输入，调用当前 HTTP Runner 使用的 Prompt 渲染函数。使用 `_build_review_request` 与 `run_provider` 在 HTTP 传输前捕获 Standard 的 OpenAI Responses 请求体。两条路径保存文件范围、系统 Prompt 和输入 Prompt 的 UTF-8 字节数及 SHA-256。用固定模型名 `fixture-model`、空项目规范、空 Memory 和空 Context Pack 文本复跑。未调用真实模型或生产环境，未运行项目单元测试。

### F1 · 规则目录与解析器

- **改动量等级：小。** 新增独立规则模块和内置资源，复用现有打包方式。
- **目标与范围**　实现规则目录加载、Pattern 编译、优先级解析、默认回退、重复规则去重、来源摘要和 catalog version。实现精确文件名、特殊路径、扩展名和可选 `.m` 内容识别。解析器输入是已纳入审查的相对路径和可选有限内容片段。
- **改动性质**　新增能力，属于局部内部模块增量。
- **历史设计影响**　不改变 changed files 的选择和过滤。不改变项目端类型配置 API。
- **页面变化**　无。
- **验收**　逐条验证优先级、大小写和路径分隔符、Windows 路径、重复规则、未命中回退、规则文件缺失、非法 Pattern、`.m` 无法读取和多文件解析顺序。验证任何解析异常都能回退并留下原因码。
- **停止点**　解析器在固定样本上结果稳定，规则资产版本可计算后停止。

### F2 · Agent / Standard 请求注入

- **改动量等级：中。** 两条请求链路共用规则构建和字节预算，复用现有 Runner、Provider、Review Card 和任务状态。
- **目标与范围**　为安全审查路径解析主规则，记录规则键、Pattern、来源和版本。Agent 和 Standard 使用同一解析器，重复规则正文注入一次。Agent 队列快照保存本次规则段和摘要，MR 的既有修复复审快照保存规则版本。
- **改动性质**　请求构建增量，不重构 Runner。
- **历史设计影响**　`reviewInstructions` 和 `baselineContext` 继续兼容。模型输出 schema、Finding 归属和通知链路不变。Prompt 长度增加，必须纳入现有 token 预算和裁剪摘要。
- **页面变化**　首版不变，执行过程可追加规则摘要事件。
- **验收**　用纯 Java、纯 TypeScript、Mapper + Java + POM、普通 XML 和全栈混合 diff 检查实际 Provider 请求。确认每个文件只命中一个主规则，多个文件可共享同一规则正文，规则块包含正确路径，未命中回退 default，Agent 与 Standard 的规则摘要一致。
- **停止点**　两条 Review 入口都能生成同一规则映射，旧请求和旧任务仍可完成后停止。

### F3 · 项目端类型兼容与自动接入

- **改动量等级：大。** 调整项目创建和 MR / Push 主链路的默认 Profile 与门控，须一起验证自动触发、既有 Profile、风险提醒和结果。
- **目标与范围**　新项目没有显式 `targetType` 时继续进入 Review。已有显式类型作为可选项目级 Prompt。多端自动检测结果保存到 `detected_target_types`，作为诊断和规则辅助，不单独阻断文件规则请求。需要项目级 Provider / Profile 时沿用已有显式配置，没有配置时使用既有默认配置。
- **改动性质**　局部调整项目创建默认值和端类型门控，沿用现有项目配置模型。
- **历史设计影响**　移除 MR / Push 因自动检测到多端且未选主端而创建失败任务的分支。既有失败记录仍可查阅。沿用全局开关、事件策略、Profile 启用校验、提醒模板和通知配置。
- **页面变化**　项目设置入口沿用现有页面。新项目无需先选择端类型，项目设置仍可维护项目级 Profile。
- **验收**　新建无端类型项目直接审查。混合 Backend + Web 变更按文件生成不同规则。已有 Backend 项目 Prompt、Provider、Profile 和通知不变。显式项目类型和自动检测结果冲突时，文件规则仍可生成并保留冲突摘要。
- **停止点**　新项目直入审查和旧项目兼容均闭环后停止。

### F4 · 规则来源可观测与回放

- **改动量等级：中。** 后端进度接入既有任务详情抽屉，覆盖 Agent、Standard 与历史事件兼容。
- **目标与范围**　保存规则目录版本、文件命中数量、回退数量、解析错误数量和每个文件的规则键摘要。完整规则正文仍只在受控 Prompt / 回放中读取。请求失败时能定位是规则资源、构建、预算还是 Provider 问题。
- **改动性质**　观测增量。
- **历史设计影响**　只增加白名单元数据，不改变正式结果和通知。
- **页面变化**　任务详情的「上下文准备」抽屉增加规则摘要。
- **验收**　规则版本变化、规则缺失、回退、旧任务、重试、Agent / Standard、敏感路径和超长摘要均可查询。规则正文和凭据不会进入进度或遥测。
- **停止点**　规则命中可以追到请求和任务后停止。

### F5 · 正常入口生产验收与回退

- **改动量等级：中。** 需要跨 MR、Push、manual Review、Agent、Standard 和结果页面做闭环核验。
- **目标与范围**　使用正常 Review 入口对新项目、旧项目、混合项目和规则未命中文件进行验证。比较文件规则上线前后的 Prompt 映射、模型用量、Finding 类型、误报、漏报和失败率。规则目录版本固定，发现规则正文问题时更新 catalog version。
- **改动性质**　验收和版本发布增量。
- **历史设计影响**　历史任务按记录的 catalog version 继续解释。通过回退应用版本恢复改前 Prompt 和端类型路由，保留规则快照与历史结果。
- **页面变化**　主页面布局保持稳定，确认规则摘要、Finding、任务状态和通知链接均可用。
- **验收**　至少覆盖：新项目无端类型、显式 Backend 项目、混合全栈项目、Mapper + Java + POM、普通 XML、规则缺失、Agent 失败后 Standard fallback、重试和历史结果读取。只有人工标注样本用于准确率结论，未标注数据只用于观测。
- **授权边界与停止点**　开发分支完成本地验收后交付。生产验证由用户安排，验证后在本文记录规则覆盖、失败原因、Prompt 增量和遗留规则清单。

### F1–F5 本地验收记录

2026-11-28，F1–F4 已实现，F5 本地闭环通过。生产 Provider、MySQL 实例和人工标注准确度待生产验证。

| 阶段 | 本地验收 |
| --- | --- |
| F1 | 对照 F0 校验固定提交的 74 条映射、70 份正文和许可证。核对 30 个文件预期、大小写、Windows 路径、嵌套路径、同正文去重、非法模式和资源缺失。 |
| F2 | 通过正常手动入口捕获 Standard Provider 请求和 Agent 队列领取后的 HTTP Runner 请求。对同一全栈输入核对两条请求的规则正文与路径完全一致。通过替身模型验证 Agent 提交 Review Card 和正式结果落库。 |
| F3 | 在隔离 SQLite 中通过项目创建、MR 和 Push 入口验证。全栈项目保存 Web 和 Backend 检测结果，正常进入文件规则 Review。显式 Backend 项目保留原 Profile、风险提醒开关及通知记录。Push 经现有分支与触发策略，人工重试同一模型后只有一份正式结果。 |
| F4 | 通过任务进度 API 核对匹配明细和规则目录摘要。用 2,000 路径验证字节预算与摘要裁剪，核对敏感路径、规则正文和请求预览。前端构建通过，核对现有抽屉的规则摘要和历史任务空态。 |
| F5 | 模拟 Agent 租约过期后重领及执行超时，验证 Agent 输入与 Standard 降级复用原规则快照。模拟规则资源缺失，常规 Review 继续完成并记录回退原因。普通 XML、Vue、Svelte 等走通用规则。 |

#### 正常入口与回退

1. 取 F0 的全栈和特殊文件样本。在项目创建时省略 `targetType`，用同一变更分别执行手动 Agent 和 Standard Review。核对任务详情「执行过程 → 上下文准备」的目录版本、命中、回退和裁剪。需要逐文件核对时读取 `GET /api/review-tasks/{taskId}/code-quality-progress?reviewKey=…`。
2. 用相同变更分别触发 MR 和启用自动审查的 Push，核对 Profile、正式结果、任务状态和原有通知。另用显式 Backend 项目核对其原有 Profile 和通知路由。对同一 Push 点重试，核对进度版本和正式结果。
3. 将 Agent 超时后的 Standard 降级结果与入队进度对比。Agent 续领和执行失败后降级复用本次已入队的规则快照。用户点击重试会发起新执行，并记录当时启用的规则版本。历史任务可以缺少规则事件。
4. 如需回退，先处理在途 Agent 任务，再回退应用版本。已经创建并使用 `file-default-ai-review` 的项目须保留该数据库 Profile 记录。历史审查结果及进度可使用原有读取入口。

改动文件 Ruff、差异检查和前端构建通过。全仓 Ruff 报告四项已有 lint 问题。未运行单元测试，未连接真实模型或生产服务。

## 5. 接口和内部数据建议

`FILE_RULES_RESOLVED` 复用任务进度接口。`detail` 保存以下结构，值以本次审查为准。

```json
{
  "catalogVersion": "<sha256>",
  "matchedCount": 1,
  "fallbackCount": 0,
  "errorCount": 0,
  "contentUnavailableCount": 0,
  "promptBytes": 2400,
  "promptTruncated": false,
  "filesTruncated": false,
  "files": [
    {
      "path": "backend/src/main/resources/OrderMapper.xml",
      "ruleKey": "mapper_dao_xml",
      "pattern": "**/*{mapper,dao}*.xml",
      "source": "SYSTEM_FILE_RULE",
      "fallback": false
    }
  ]
}
```

每条文件记录可带 `CONTENT_SNIFF_UNAVAILABLE` 或 `FILE_RULE_RESOLUTION_FAILED`。规则正文随模型输入发送。规则段从 Standard 请求预览中移除。Agent 顶层队列输入保存本次规则段及摘要供降级使用，Worker 继续从原有 `reviewInstructions` 读取指令。已有自动修复复审快照可增量记录 `fileRuleCatalogVersion` 来检查原审查与复审时的目录一致性。

## 6. 首版验收矩阵

| 场景 | 预期 |
|---|---|
| Java 文件 | 命中 Java 规则，不依赖项目端类型才能开始审查 |
| C / Objective-C 文件 | `.c` 命中 C，`.mm` 命中 Objective-C，`.m` 按内容区分 Objective-C 与 MATLAB，`.h` 走通用回退 |
| Mapper XML | 命中 Mapper 规则，普通 XML 不命中 Mapper 规则 |
| POM | 命中 Maven 规则，父 POM 版本管理可作为上下文核对 |
| 混合全栈 MR | 每个文件有自己的规则块，项目级规则可追加 |
| 没有项目端类型 | Review 正常进入，使用文件规则和通用回退 |
| 多个自动检测端类型 | 保存检测摘要，不因文件规则本身阻断 Review |
| 规则资源缺失 | 回退 default 或现有通用 Prompt，记录错误原因 |
| Agent / Standard | 使用同一规则映射和 catalog version |
| 历史任务 | 按原有规则快照或旧请求继续可读 |

## 7. 上游参考

- [OCR system_rules.json](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/config/rules/system_rules.json)
- [OCR rule documents](https://github.com/alibaba/open-code-review/tree/d4f568f/internal/config/rules/rule_docs)
- [OCR rule resolution](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/config/rules/system_rules.go)
- [OCR mixed-file rule injection](https://github.com/alibaba/open-code-review/blob/d4f568f/internal/agent/agent.go#L1751)
- [OCR review rules documentation](https://github.com/alibaba/open-code-review/blob/d4f568f/pages/src/content/docs/zh/review-rules.md)
