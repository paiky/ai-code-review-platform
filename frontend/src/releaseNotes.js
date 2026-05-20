export const releaseNotes = [
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
