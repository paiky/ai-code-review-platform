## Project
AI 变更风险审查平台（MVP）

## Product goal
构建一个可接入 GitLab / Jenkins / 钉钉的研发质量平台。
输入代码变更（MR、commit range、branch diff），输出结构化风险卡片。
首期聚焦后端项目中的接口、数据库、缓存、MQ、配置变更识别。
后期支持前端、后端、通用模板的自定义审查。

## Non-goals
- 不做 IDEA 插件为主入口
- 不做复杂全仓库架构图
- 不做重型实时分析
- 不追求一次性覆盖所有规则

## MVP scope
1. 接收 GitLab MR webhook
2. 拉取 diff / changed files
3. 分析变更类型：接口、DB、缓存、MQ、配置
4. 结合规则生成风险项
5. 生成风险卡片
6. 通过钉钉推送
7. 保存审查记录到数据库
8. 提供一个简单 Web 页面查看记录

## Tech principles
- 模块化
- 配置优先
- 审查规则模板化
- 风险输出结构化
- 先规则、后 AI，AI 作为增强而非唯一依赖
- 所有功能必须可测试
- 所有接口必须有清晰 DTO / VO / schema

## Architecture preference
- backend: Java Spring Boot
- db: MySQL
- cache: Redis (optional later)
- messaging: keep abstraction only in MVP
- frontend: React + Ant Design or Vue + Element Plus（选一个）
- webhook-driven, async job capable
- clean package structure

## Core domain modules
- project-integration
- change-analysis
- risk-engine
- rule-template
- review-record
- notification
- knowledge-base (placeholder in MVP)

## Required outputs
- 风险卡片 JSON schema
- 审查记录表结构
- 管理后台基础页面
- GitLab webhook controller
- DingTalk notifier
- rule engine with configurable rules

## Working style
- 新对话理解项目时，先读 `AGENTS.md`、`README.md`，再按任务需要阅读 `docs/` 下相关设计文档。
- 在 Windows PowerShell 中阅读中文 Markdown / 文档时，优先使用 `Get-Content -Raw -Encoding UTF8 <path>`，避免默认编码导致中文乱码并影响理解。
- 本地启动、编译、测试、构建优先使用仓库 `scripts/` 目录下脚本，不要直接按个人习惯拼 `mvn` / `npm` 命令。
- 后端启动使用 `scripts/run-backend.cmd`；需要传 Maven 目标时也通过该脚本传参，例如 `scripts/run-backend.cmd -q test`、`scripts/run-backend.cmd -q -DskipTests compile`。
- 前端启动使用 `scripts/run-frontend.cmd`；需要构建时使用 `scripts/run-frontend.cmd build`。
- 只有脚本缺少所需能力或脚本本身失败且需要定位根因时，才直接进入 `backend/` 或 `frontend/` 执行底层命令，并在结论中说明原因。
- 每次只做一个小目标
- 先写设计，再实现
- 先补充 README，再写代码
- 先写数据结构与接口，再写业务逻辑
- 后续落地的多阶段推进计划文档，必须在文档中写清分阶段落地 prompt、总控 prompt、Agent 可按总控 prompt 自主推进的授权边界，并明确每个阶段完成后必须停止，等待用户验证并确认“继续下一阶段”后再推进。可参考 `docs/19-python-backend-refactor-plan.md` 的分阶段 prompt 写法。
- 完成后必须补测试与示例数据
- 所有 PR/patch 必须附带“改了什么、为什么、如何验证”
- 遇到问题或异常现象时，先查阅 `docs/10-local-dev-pitfalls.md` 是否已有解决方式。
- 新解决的踩坑、误判根因、环境问题或调试结论，完成后必须补充到 `docs/10-local-dev-pitfalls.md`。

## Definition of done
- 能本地跑通
- 至少有一个 webhook -> 分析 -> 风险卡片 -> 推送 -> 落库 的完整链路
- 有 demo 数据
- 有最小前端页面
- README 写清启动方式与验证步骤
