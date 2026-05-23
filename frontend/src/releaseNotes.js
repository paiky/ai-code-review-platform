export const releaseNotes = [
  {
    id: '2026-05-23-multi-target-project-groups',
    version: 'v0.11.0',
    releaseDate: '2026-05-23',
    title: '多端接入、项目组与 AI Review 配置升级',
    summary: '平台从单一后端审查模型升级为项目可多端接入，新增项目组、端类型配置、路径识别和多端 AI Review Profile，并修复设置页在多端场景下的关键体验问题。',
    highlights: [
      '新增项目组与项目端类型配置，任务列表可按项目组、项目和端类型筛选。',
      'GitLab webhook 会根据 changed files 自动识别 BACKEND、WEB_PC、iOS、Android 和跨端项目，并记录识别依据。',
      '支持预创建还没有触发 webhook 的 GitLab 项目，首次 webhook 进入时可复用已配置项目组和端类型。',
      'PC / APP 端默认使用各自 AI Review Profile，提醒卡片默认只对后端端类型显示。',
      '项目端类型配置支持按 webhook 识别结果一键回填路径匹配，减少手动维护成本。',
      'AI Review Profile 的“恢复默认”会恢复当前 Profile 自己的默认 Prompt，不再把 PC / APP 模板覆盖成后端模板。',
      'Push 审核策略中最大文件数和最大 Diff 字节默认改为 -1，表示不设置硬上限。'
    ],
    tags: ['多端接入', '项目组', '路径识别', 'AI Review', 'Push 审核']
  },
  {
    id: '2026-05-22-maintainable-reminder-artifacts',
    version: 'v0.10.0',
    releaseDate: '2026-05-22',
    title: '提醒项可维护内容升级',
    summary: '提醒卡片从“提示风险”进一步升级为“给出可复制维护产物”，DB、Redis、MQ 与 Nacos 配置提醒会尽量产出可保存、可维护的脚本或配置片段。',
    highlights: [
      '提醒项新增“可维护内容”区域，支持复制 SQL、Redis 命令、MQ 配置伪代码与 Nacos 配置块。',
      'DB 提醒优先展示真实 DDL；没有 SQL 文件时，会根据 Entity / Mapper 和变更类型推断 `CREATE TABLE` 或 `ALTER TABLE` 草稿，并标记 `INFERRED`。',
      '新增表场景会按 `@TableName` 生成 `CREATE TABLE` 草稿，已有表字段变更则生成 `ALTER TABLE ... ADD COLUMN ...` 草稿。',
      '多张表同时命中时按表拆分维护 SQL，避免把不同表字段混到同一段脚本里。',
      '提醒项保留原命中证据，并新增 Diff 查看入口，可直接查看对应文件的左右对照变更。'
    ],
    tags: ['提醒卡片', '维护 SQL', 'DB 规则', 'Diff 查看']
  },
  {
    id: '2026-05-21-ai-review-diff-fix-preview-scheduler',
    version: 'v0.9.0',
    releaseDate: '2026-05-21',
    title: 'AI Review Diff、修复预览与调度队列升级',
    summary: 'AI Review 从“指出问题”升级到“定位变更、预览修复、可观测调度”的完整闭环，质量问题可以直接查看左右对照 diff，并在后台生成可审阅的 unified diff 修复 patch。',
    highlights: [
      '质量问题支持“查看 Diff”弹窗，按文件展示左右对照变更，并高亮模型返回的目标行号。',
      '每条 finding 支持生成 AI 修复 Patch 预览，只展示 unified diff，不修改仓库、不提交 MR。',
      'AI Review 成功后会自动为可匹配 diff 的 finding 排队生成修复预览，刷新页面后仍可查看已持久化结果。',
      '新增统一 Provider 调度队列：AI Review 优先于修复预览，全局最多 10 个并发，修复预览区分排队中与生成中。',
      '任务列表页新增调度队列入口，可查看 Review 任务及其风险点修复预览的排队、运行和完成明细。',
      '任务详情页取消轮询时的全屏遮罩，AI Review 运行中仅在执行过程顶部显示轻量 loading 和已执行秒数。'
    ],
    tags: ['AI Review', 'Diff 查看', '修复预览', '调度队列']
  },
  {
    id: '2026-05-20-routing-release-center',
    version: 'v0.8.0',
    releaseDate: '2026-05-20',
    title: '页面路由与版本中心升级',
    summary: '前端从单页状态切换升级为真实页面路由，任务、设置与版本更新都具备独立 URL，并补齐返回上一层体验。',
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
    summary: '代码质量 AI Review 进一步收口到稳定的非流式调用路径，并强化任务过程展示与失败诊断。',
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
    summary: 'GitLab Push Hook 与 MR Hook 共用主入口，平台可按真实 compare diff 或 payload 文件列表继续完成提醒分析。',
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
    summary: '提醒卡片从粗粒度的 DB / MQ / 缓存分类，扩展到更可解释的细分类型，前端展示也更贴近真实排查动作。',
    highlights: [
      'DB 细分识别覆盖表结构、SQL、ORM 映射、实体模型与数据迁移场景。',
      'MQ 与缓存提醒可区分生产者、消费者、消息结构、Key、TTL、失效与序列化问题。',
      '卡片支持展示命中原因、证据与关联信号，降低误判后的排查成本。'
    ],
    tags: ['提醒卡片', '细粒度规则', '前端展示']
  }
];
