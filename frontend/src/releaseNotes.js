export const releaseNotes = [
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
