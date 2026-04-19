# AI 变更风险审查平台 MVP 产品概览

## 1. 产品定位

AI 变更风险审查平台是一个接入研发流程的质量保障平台。它围绕代码变更本身进行影响面分析与风险识别，在 Merge Request、构建或发布前等关键节点生成结构化风险卡片，帮助 reviewer、测试、发布负责人快速聚焦高风险变更。

一期 MVP 不以 IDE 插件为主入口，也不追求复杂全仓库静态分析。MVP 的核心目标是打通一条可运行、可验证、可扩展的最小闭环：

```text
GitLab MR webhook
  -> 拉取或接收 diff / changed files
  -> 识别接口、数据库、缓存、MQ、配置变更
  -> 按 backend-default 规则模板生成风险项
  -> 生成结构化风险卡片
  -> 钉钉推送
  -> 审查任务与结果落库
  -> Web 页面查看记录
```

## 2. MVP 目标用户

- 后端开发工程师：提交 MR 后获得自动风险提示。
- Reviewer：根据风险卡片优先审查关键变更。
- 测试工程师：根据影响面和检查项设计回归范围。
- 发布负责人：上线前确认灰度、回滚、监控、告警等保障事项。
- 技术负责人：沉淀团队规则模板和高频风险模式。

## 3. MVP 核心价值

1. 让代码审查从“盲审 diff”转向“围绕变更风险聚焦”。
2. 将审查结果从大段文本转成可展示、可推送、可落库的结构化风险卡片。
3. 用规则模板先覆盖典型后端风险，后续再引入 AI 增强。
4. 保留平台化扩展空间，支持未来接入 Jenkins、手动审查、前端模板和知识库。

## 4. MVP 范围

### 4.1 必做能力

- 接收 GitLab Merge Request webhook。
- 创建 ReviewTask 审查任务并保存任务状态。
- 获取或接收 changed files 与 diff 内容。
- 分析五类变更类型：
  - API：Controller、接口路径、请求响应 DTO。
  - DB：SQL、Mapper、Entity、Migration。
  - CACHE：Redis key、缓存读写、缓存失效。
  - MQ：生产者、消费者、Topic、Tag、消息体。
  - CONFIG：YAML、properties、Nacos 配置、开关项。
- 使用默认规则模板 `backend-default` 生成风险项。
- 生成风险卡片 JSON。
- 通过钉钉 webhook 推送风险卡片摘要。
- 保存审查结果、风险卡片和推送记录。
- 提供最小 Web 页面查看审查任务列表和详情。

### 4.2 暂不做能力

- 不做 IDEA 插件作为主入口。
- 不做复杂调用图、全链路静态分析或实时分析。
- 不做完整权限体系。
- 不做多模型动态路由。
- 不依赖 AI 作为唯一判断来源。
- 不在一期覆盖所有语言和所有框架。

## 5. 输入与输出

### 5.1 输入

MVP 支持以下输入来源，优先级从高到低：

1. GitLab MR webhook payload。
2. GitLab API 获取的 changed files 与 diff。
3. 本地或测试环境中的 demo webhook payload 与 demo diff。

核心输入字段包括：

- projectId / projectPath
- mergeRequestIid
- sourceBranch
- targetBranch
- commitSha / beforeSha / afterSha
- author
- reviewer
- changedFiles
- diffText

### 5.2 输出

MVP 输出三类结果：

1. 风险卡片 JSON：供前端渲染、钉钉推送和数据库保存。
2. 审查任务记录：记录触发来源、任务状态、模板、耗时、错误信息。
3. 推送记录：记录推送渠道、目标、请求摘要、响应状态和失败原因。

## 6. 成功标准

MVP 完成时应满足：

- 能本地启动后端、前端和数据库。
- 能用 demo GitLab webhook payload 触发一条审查任务。
- 至少能识别 API / DB / CACHE / MQ / CONFIG 中的若干典型变更。
- 能生成符合 schema 的风险卡片 JSON。
- 能保存项目、审查任务、审查结果、规则模板、推送记录。
- 能在 Web 页面查看任务列表、任务详情和风险卡片。
- 钉钉 webhook 配置存在时能推送；未配置时可记录跳过或失败原因。
