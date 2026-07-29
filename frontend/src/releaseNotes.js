export const releaseNotes = [
  {
    id: '2026-07-29-agent-review-worker-pool-queue-governance-1-2-0',
    version: 'v1.2.0',
    releaseDate: '2026-07-29',
    title: 'Agent Review 多 Worker 池与队列运行治理',
    summary: '平台升级至 1.2.0：Agent Review 从单 Worker 执行升级为具备安全并发领取、两副本 Worker Pool、实时队列与容量治理、SIGTERM 优雅排空和一键顺序升级的运行体系；全部容量忙碌时任务继续排队，既有租约 fencing、最大尝试次数与 Standard fallback 边界保持不变。',
    highlights: [
      '并发领取增加 claimAttempt fencing：Worker 心跳、完成、失败和取消都会校验领取者与尝试次数；租约过期后可由其它 Worker 安全接管，旧 Worker 的迟到请求不会覆盖新结果。',
      '新增 Worker 注册池和安全节点白名单，生产环境使用两个 capacity=1 的独立 Worker；设置页可查看在线、空闲、忙碌、排空和最近心跳，旧单 Worker 与历史数据继续兼容。',
      '调度顺序保持 priority DESC + queuedAt ASC；全部在线 Worker 为 BUSY 时，新任务保持 QUEUED，不会被误判为 Worker 离线，也不会仅因容量忙碌触发 Standard fallback。',
      'Agent Settings 和设置页新增排队、运行、过期租约、最老等待、在线与忙碌容量、利用率及 DRAINING 数量，并提供离线、全忙、积压和租约接管安全告警。',
      'Worker 支持 SIGTERM 优雅排空：进入 DRAINING 后立即停止领取新任务，继续心跳并完成当前任务；固定宽限期耗尽后仍由既有租约和 claimAttempt fencing 接管。',
      '任务详情继续只展示脱敏领取尝试和 AGENT_RECLAIMED 接管事件，不暴露 Worker 基础设施、异常原文、Prompt、源码、模型内容或推理。',
      '新增 deploy-stage3.sh，支持 status、preflight、upgrade 和显式人工 scale；升级按 Backend、队列闸门、Worker Pool、Frontend 的安全顺序执行，不引入自动扩缩容。'
    ],
    tags: ['1.2.0', 'Agent Review', 'Worker Pool', '安全并发', '队列治理', '优雅排空', '部署升级']
  },
  {
    id: '2026-07-24-agent-review-observability-1-1-0',
    version: 'v1.1.0',
    releaseDate: '2026-07-24',
    title: 'Agent Review 正式上线与智能审查升级',
    summary: '平台升级至 1.1.0：Agent Review 已具备按项目组安全启用、独立 Worker 稳定执行、失败自动降级、全链路可观测和脱敏治理能力；完成 DeepSeek 配置与源码外发授权后，即可接入正式生产 Review，STANDARD 继续作为可选主引擎和可靠 fallback。',
    highlights: [
      'Agent Review 正式接入 MR、Push 和 Manual Review 主链路；项目组可在 STANDARD 与 AGENT 之间选择主引擎，Agent 成功结果统一进入现有 finding、任务详情和通知链路。',
      '生产执行具备明确的可靠性保障：Agent 不可用、超时或执行失败时记录真实原因并自动执行 STANDARD_FALLBACK，不会阻断 Review，也不会把降级结果伪装为 Agent 成功。',
      '新增独立 Agent Worker、加密 API Key、任务级只读 worktree 和受限 MCP 工具；Agent 可按需读取 diff、搜索调用方与相关源码，但不能执行命令、写文件、访问其它项目或绕过 DeepSeek-only 出站限制。',
      '质量看板提供 STANDARD / AGENT 样本和同任务配对观察，持续展示人工标注进度、误判、漏报、上下文不足、成功率、fallback、p50/p95、turn、工具调用和源码返回量，为生产运营和后续扩大范围提供数据依据。',
      '新增强制脱敏的 Agent 对照摘要导出和合成 Demo；导出不包含源码、完整 diff、API Key、Prompt、模型思维过程、会话内容或 MCP 返回源码。',
      '首次 Review 前确定性 Preflight 已接入调度链路，Planner 增加端类型、语言、提取器版本和覆盖模式摘要，为后续评估驱动的多端 Planner / Retriever 扩展建立基线。',
      '完善 Windows + Docker Desktop 一键启动、局域网上游代理、Linux Compose 部署、Worker 健康检查和 MySQL 5.7 Job claim 兼容；生产仍推荐 MySQL 8.0+。'
    ],
    tags: ['1.1.0', 'Agent Review', 'Claude Code', 'DeepSeek', '正式上线', '可靠降级', '只读 MCP', '部署升级']
  },
  {
    id: '2026-07-10-quality-governance-mui-1-0-0',
    version: 'v1.0.0',
    releaseDate: '2026-07-10',
    title: '质量治理中心与全站主框架升级',
    summary: '平台进入 1.0.0：新增质量治理下的看板、评估样本、高级诊断、验收记录和回放记录，并完成主要页面的 MUI 外层布局重构，让日常 Review、质量治理和配置管理形成更清晰的后台工作台体验。',
    highlights: [
      '新增“质量治理”统一入口，集中进入质量看板、评估样本、规则缺口、验收记录和回放记录；反馈池继续默认隐藏，仅在 feature flag 开启后展示。',
      '质量看板聚合评估样本、误判率、上下文不足率、等级偏差、重复 finding、漏报样本，以及补证据、确定性检查、回放和验收记录摘要。',
      '评估样本支持从 AI finding 或人工漏报沉淀质量样本，并可维护规则缺口归因，用于判断误判、漏报或上下文不足是否真的和某类缺口相关。',
      '规则缺口、验收记录和回放记录收敛为高级诊断页，保留直接路由和后端能力，但不再占据默认主入口。',
      '新增验收记录与回放记录，用于记录 Retriever、Prompt、Context Pack、确定性检查或 Provider 改动的准入、退出结果和 baseline / candidate 对比。',
      '前端完成 MUI / Material 3 基础设施和主要页面外层布局迁移，覆盖质量治理、任务列表、任务详情、设置、版本更新和接入帮助页。',
      '后台 UI 收敛为紧凑可扫描布局：页头只保留标题和说明，纯刷新按钮和分类标注从页头移除，列表、Top 维度和记录类内容继续保留表格呈现。',
      '质量治理和任务页的 API 契约、任务直达链接、reviewKey 参数、AI Review 轮询、Diff viewer、Patch 预览和复杂设置表单保持兼容。'
    ],
    tags: ['1.0.0', '质量治理', '评估样本', '规则缺口', '验收记录', '回放记录', 'MUI', 'UI 重构']
  },
  {
    id: '2026-06-15-rule-gap-recommendations',
    version: 'v0.17.0',
    releaseDate: '2026-06-15',
    title: '高准确模式补齐建议：字段证据、预算保护与规则缺口推荐',
    summary: '高准确模式继续从“能检索证据”升级到“知道还缺什么、是否值得补”。本版补齐结构化字段引用检索、预算裁剪保护和规则缺口补全建议，帮助管理员判断下一阶段应该优先补哪类能力。',
    highlights: [
      '结构化字段变更会补充本地引用搜索，帮助判断字段调整是否影响调用、映射、序列化或外部交互，降低只看 diff 导致的误判。',
      '预算裁剪会优先保护高误判 signal 的关键证据；放不进模型输入的证据会保留安全摘要，提示存在未注入证据。',
      'Finding 输出被强化为受上下文完整性约束：关键证据缺失时，应使用部分或不足的上下文状态，并避免高置信结论。',
      '补充 Finding 级二阶段补证据设计：后续只围绕少数候选 finding 再补证据，不无差别扩大第一阶段输入。',
      '规则缺口看板新增“建议补全”视图，按频率、影响范围、误判反馈、实现可行性和复杂度给出是否建议补、补全类型、下一阶段和可复制 prompt。',
      '推荐结果只作为人工决策入口，不会自动改规则、自动改 Prompt、自动降级、自动忽略 finding 或自动实现 Retriever。'
    ],
    tags: ['规则缺口推荐', '字段引用检索', '预算保护', '二阶段补证据', '高准确模式', 'AI Review']
  },
  {
    id: '2026-06-13-high-accuracy-local-context',
    version: 'v0.16.0',
    releaseDate: '2026-06-13',
    title: '高准确模式：本地仓库上下文检索与规则缺口看板',
    summary: '代码质量 Review 从 diff-only 审查升级为高准确模式：平台先在本地准备仓库上下文、规划需要补充的证据，再把预算内片段注入模型输入，并公开展示流转和规则缺口优先级。',
    highlights: [
      '新增 Context Pack 与 Context Planner：先识别方法、字段、DTO、DB、缓存、MQ、配置等变更信号，再决定需要补充哪些上下文证据。',
      '支持本地 mirror / worktree 准备任务源码，用本地引用检索补充删除方法、方法签名变更、DTO/字段、DB/Mapper/Entity 和缓存 key 读写链路等高价值证据。',
      '模型不会收到完整项目源码；平台只在本地检索，并把排序后、受预算限制的 bounded snippets 注入 Review 输入。',
      '任务详情新增“高准确模式流转”，按变更接入、Context Pack、Planner、本地仓库、Retriever、预算裁剪、Provider、结果解析展示执行状态。',
      '当本地仓库已准备但引用查询数为 0 时，页面会解释是没有支持的 signal、Retriever 被跳过，还是检索失败。',
      '新增“规则缺口”看板，按缺口类型、Signal、Requested Context、建议能力、项目和任务样例聚合跨任务能力缺口，用于判断后续 Retriever 补齐顺序。',
      '本地 workspace 增加清理与磁盘保护，支持 worktree TTL 清理、长期闲置 mirror 清理和安全路径校验。',
      '部署启用高准确模式时，需要 GitLab token 具备 read_repository 权限，并配置 workspace 挂载、worktree 保留时间和 mirror 保留周期。'
    ],
    tags: ['高准确模式', '本地仓库上下文', 'Context Pack', '规则缺口看板', '部署配置', 'AI Review']
  },
  {
    id: '2026-06-02-gitlab-diff-context-final',
    version: 'v0.15.0',
    releaseDate: '2026-06-02',
    title: 'GitLab Diff 上下文展开与 GLM Provider 接入',
    summary: '查看 Diff 支持完整上下文展开，AI 修复 Patch 保持紧凑代码视图，并新增智谱 GLM Provider 供 AI Review、修复预览和联通性测试使用。',
    highlights: [
      '默认保持紧凑 Diff，按需读取完整源码；隐藏区支持向上展开 20 行、向下展开 20 行和展开全部。',
      '查看 Diff 和 Patch 预览默认使用明亮主题，顶部新增太阳 / 月亮按钮，可切换为暗黑代码主题。',
      'Java、Python、JS/TS、SQL、XML、JSON、YAML、CSS、Shell 和 Markdown 支持 Prism token 级高亮。',
      'MR API 补拉保存历史 base / head refs；详情缺少 diff_refs 时回退读取最新 diff version，原地重跑旧 MR 也会刷新 refs。',
      '新增文件仅读取右侧源码，删除文件仅读取左侧源码，重命名文件分别读取 old / new 路径。',
      'Patch 预览保持紧凑展示，不再提供可能因模型 Patch 与当前源码基线不一致而失败的上下文展开入口。',
      '新增内置智谱 GLM Provider，支持配置 endpoint、model、API Key 和超时，并复用现有多模型 AI Review、修复预览和联通性测试链路。'
    ],
    tags: ['GitLab', 'Diff 上下文', 'GLM', 'Provider', 'AI Review', 'v0.15.0']
  },
  {
    id: '2026-05-29-multi-model-ai-review',
    version: 'v0.14.0',
    releaseDate: '2026-05-29',
    title: '项目组多模型 AI Review 与可中断调度',
    summary: 'AI Review 从单模型升级为项目组多模型配置，并补齐模型级调度队列与手动中断能力。',
    highlights: [
      '项目组可配置多个 AI Review 模型，MR、Push、手动触发和重试会按模型维度并行生成多份审查结果。',
      '调度队列按具体模型展示 AI Review 任务，支持只中断某一个模型 Review，不影响同一任务下其他模型继续执行。',
      '任务详情页可中断运行中或排队中的 AI Review / 修复预览；中断或失败后钉钉摘要会带上原因，方便判断是手动中断还是 Provider 异常。'
    ],
    tags: ['多模型 Review', '模型级中断', '调度队列', '钉钉原因', 'AI Review']
  },
  {
    id: '2026-05-27-xiaomimo-provider-connectivity-help',
    version: 'v0.13.0',
    releaseDate: '2026-05-27',
    title: 'XiaoMIMO 接入、Provider 联通性测试与接入帮助页',
    summary: '模型 Provider 配置升级，新增 XiaoMIMO 内置 Provider、配置联通性测试，并补齐接入帮助页。',
    highlights: [
      '新增 XiaoMIMO / Xiaomi MiMo Provider，默认模型为 mimo-v2.5-pro。',
      'Provider 配置页新增“测试联通性”按钮，可用当前表单内容验证 endpoint、model 和 API Key。',
      '新增接入帮助页，按 GitLab、钉钉、项目组、项目和模型配置串起首次接入流程。'
    ],
    tags: ['XiaoMIMO', 'Provider 测试', '接入帮助', 'AI Review']
  },
  {
    id: '2026-05-25-multi-target-review-ops',
    version: 'v0.12.0',
    releaseDate: '2026-05-25',
    title: '多端 AI Review 联调与项目组通知升级',
    summary: '完成 Android 项目真实联调，收敛多端 Prompt、项目组通知和调度队列稳定性。',
    highlights: [
      '多端 AI Review 会读取各自 Profile Prompt。',
      '钉钉机器人下沉到项目组，通知优先按项目组发送。',
      '补强调度队列性能，并新增自动修复预览开关。'
    ],
    tags: ['多端 Prompt', '项目组通知', 'Android 联调', '修复预览', '部署配置']
  },
  {
    id: '2026-05-23-multi-target-project-groups',
    version: 'v0.11.0',
    releaseDate: '2026-05-23',
    title: '多端接入、项目组与 AI Review 配置升级',
    summary: '平台从单一后端审查升级为多端接入，支持项目组、端类型和多端 AI Review Profile。',
    highlights: [
      '新增项目组、端类型配置和任务筛选。',
      'Webhook 按 changed files 自动识别端类型。',
      'PC / APP 使用各自 AI Review Profile，后端保留提醒卡片。'
    ],
    tags: ['多端接入', '项目组', '路径识别', 'AI Review', 'Push 审核']
  },
  {
    id: '2026-05-22-maintainable-reminder-artifacts',
    version: 'v0.10.0',
    releaseDate: '2026-05-22',
    title: '提醒项可维护内容升级',
    summary: '提醒卡片增加可复制维护内容，方便直接准备 DB、Redis、MQ 和 Nacos 变更。',
    highlights: [
      '支持复制 SQL、Redis 命令、MQ 伪代码和 Nacos 配置。',
      'DB 变更优先展示真实 DDL，不足时生成推断草稿。',
      '提醒项新增 Diff 查看入口。'
    ],
    tags: ['提醒卡片', '维护 SQL', 'DB 规则', 'Diff 查看']
  },
  {
    id: '2026-05-21-ai-review-diff-fix-preview-scheduler',
    version: 'v0.9.0',
    releaseDate: '2026-05-21',
    title: 'AI Review Diff、修复预览与调度队列升级',
    summary: 'AI Review 增加 Diff 定位、修复预览和调度队列，让问题处理链路更完整。',
    highlights: [
      '质量问题可直接查看左右对照 Diff。',
      'Finding 支持生成 unified diff 修复预览。',
      '新增 Provider 调度队列，区分排队和运行状态。'
    ],
    tags: ['AI Review', 'Diff 查看', '修复预览', '调度队列']
  },
  {
    id: '2026-05-20-routing-release-center',
    version: 'v0.8.0',
    releaseDate: '2026-05-20',
    title: '页面路由与版本中心升级',
    summary: '前端升级为真实页面路由，任务、设置和版本更新都支持独立访问。',
    highlights: [
      '任务列表、任务详情、设置、版本更新页已支持独立访问与分享链接。',
      '旧的 `/?taskId=` 链接会自动跳转到新的 `/tasks/:taskId` 页面。',
      '新增版本更新页，以纵向时间轴集中展示每次重点变化。'
    ],
    tags: ['路由升级', '页面体验', '版本更新']
  },
  {
    id: '2026-05-18-ai-review-stability',
    version: 'v0.7.0',
    releaseDate: '2026-05-18',
    title: 'AI Review 稳定性与可观测性增强',
    summary: 'AI Review 收口为稳定非流式调用，并增强执行过程和失败诊断。',
    highlights: [
      '支持 OpenAI、Anthropic、DeepSeek 与自定义兼容 Provider 的统一配置。',
      '任务详情页可查看 AI Review 进度事件、结果摘要与主要问题列表。',
      '失败场景会保留更多诊断信息，便于定位请求、响应与解析问题。'
    ],
    tags: ['AI Review', 'Provider', '稳定性']
  },
  {
    id: '2026-05-15-push-diff-analysis',
    version: 'v0.6.0',
    releaseDate: '2026-05-15',
    title: 'Push Hook 与真实 Diff 分析打通',
    summary: 'GitLab Push Hook 接入主链路，支持 compare diff 和 payload 文件列表。',
    highlights: [
      'Push 触发支持 `beforeSha -> afterSha` 的 compare diff 拉取与 fallback。',
      'MR payload 缺少 changed files 时，可通过 GitLab API 自动补拉变更内容。',
      '主链路保持统一：接收事件、分析变更、生成提醒卡片、推送通知并落库。'
    ],
    tags: ['GitLab', 'Push Hook', 'Diff']
  },
  {
    id: '2026-05-10-fine-grained-reminders',
    version: 'v0.5.0',
    releaseDate: '2026-05-10',
    title: '细粒度提醒卡片第一轮完成',
    summary: '提醒卡片从 DB / MQ / 缓存粗分类扩展到更可解释的细分类型。',
    highlights: [
      'DB 细分识别覆盖表结构、SQL、ORM 映射、实体模型与数据迁移场景。',
      'MQ 与缓存提醒可区分生产者、消费者、消息结构、Key、TTL、失效与序列化问题。',
      '卡片支持展示命中原因、证据与关联信号，降低误判后的排查成本。'
    ],
    tags: ['提醒卡片', '细粒度规则', '前端展示']
  }
];
