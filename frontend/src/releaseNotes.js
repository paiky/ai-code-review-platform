export const releaseNotes = [
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
      '支持本地 mirror / worktree 准备任务源码，用本地引用检索补充删除方法、方法签名变更等高价值证据。',
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
