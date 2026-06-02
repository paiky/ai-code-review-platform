## Project
AI 变更提醒与代码质量审查平台

## Product goal
构建一个可接入 GitLab / 钉钉 / 多模型 Provider 的研发质量平台。
输入代码变更（MR、Push、manual review、commit range、branch diff），先输出结构化“提醒卡片”，再按配置触发代码质量 AI Review。
当前主线分为两类能力：
- 规则驱动的变更提醒：聚焦接口、数据库、缓存、MQ、配置等高价值变更识别。
- AI 驱动的代码质量审查：聚焦正确性、数据一致性、安全性、事务、并发、测试与可维护性问题。
后续继续支持前端、后端、通用模板的细分审查与项目级配置。

## Current scope
1. 接收 GitLab `Merge Request Hook` 与 `Push Hook`，并支持手动审查入口
2. 拉取或补拉 diff / changed files，兼容 MR diff、Push compare 和 payload fallback
3. 分析变更类型：接口、DB、缓存、MQ、配置，并支持细粒度子类型识别
4. 结合规则模板生成提醒项与结构化提醒卡片
5. 保存审查任务、分析结果、提醒卡片、通知记录到数据库
6. 通过前端查看任务列表、任务详情、提醒卡片、分析结果与原始事件摘要
7. 通过钉钉推送规则提醒或合并后的 AI Review 结果
8. 按项目 / 全局配置触发代码质量 AI Review，支持手动触发、MR 自动触发、重试与进度展示
9. 支持 AI Review provider、profile、prompt、默认 provider、钉钉 webhook 等设置管理
10. 支持项目组、端类型、项目端类型配置和多端默认 AI Review Profile
11. 支持 AI Review 调度队列、finding 级修复预览和 Push 审核策略
12. 支持本地脚本启动、测试、迁移与 Docker 部署打包

## Tech principles
- 模块化
- 配置优先
- 审查规则模板化
- 提醒输出结构化
- 先规则、后 AI，AI 作为增强而非唯一依赖
- 所有功能必须可测试
- 所有接口必须有清晰 DTO / VO / schema

## Architecture preference
- backend: Python FastAPI (`backend-python/`) is the active backend.
- legacy backend: Java Spring Boot (`backend/`) is no longer maintained and should only be used as historical reference when explicitly needed.
- db: MySQL
- runtime: Python 3.12+ for active backend; JDK / Maven are only needed for the legacy Java reference backend.
- cache: Redis related change analysis is supported; runtime cache dependency remains optional by feature
- messaging: keep abstraction, focus on MQ / event change analysis rather than heavy runtime messaging infrastructure
- frontend: React + Ant Design (`frontend/`) is the active frontend
- integrations: GitLab webhook + GitLab API, DingTalk webhook, multi-provider AI Review
- webhook-driven, async job capable
- clean package structure

## Core domain modules
- project-integration
- change-analysis
- risk-engine
- rule-template
- review-record
- notification
- code-quality-review
- settings / provider-config
- knowledge-base (placeholder, not current delivery focus)

## Required outputs
- 提醒卡片 JSON schema
- 审查记录、通知记录、AI Review 结果与进度事件表结构
- 任务列表 / 任务详情页 / 设置页 / 版本更新页
- GitLab webhook controller / manual review API / rerun API
- DingTalk notifier 与通知配置
- rule engine with configurable templates and focus change types
- AI Review provider / profile / settings / prompt management
- 本地启动、测试、迁移、部署与示例数据文档

## Working style
- 新对话理解项目时，先读 `AGENTS.md`、`README.md`，再按任务需要阅读 `docs/` 下相关设计文档。
- 在 Windows PowerShell 中阅读中文 Markdown / 文档时，优先使用 `Get-Content -Raw -Encoding UTF8 <path>`，避免默认编码导致中文乱码并影响理解。
- 后续开发以后端 Python 为主，默认只维护 `backend-python/` 与 `frontend/`。`backend/` Java 后端已停止维护，不再新增实现、测试或编译验证，除非用户明确要求对照历史行为。
- 搜索代码时必须避开依赖和构建产物目录，例如 `frontend/node_modules/`、`frontend/dist/`、`backend/target/`、`backend-python/.venv/`、`__pycache__/`、`.pytest_cache/`、`.codegraph/`。使用 `rg` 时遵守仓库根目录 `.rgignore`，不要用会扫进这些目录的全盘搜索。
- 从业务逻辑、异常现象或架构问题出发排查 Python 后端时，优先使用 CodeGraph MCP 的 `codegraph_context` 获取候选模块和关键符号，再用 `rg` 核对真实调用位置、接口路径、配置字段和错误文案。
- 已知接口路径、字段名、错误信息、日志内容或目标字符串时，优先直接使用 `rg`。前端搜索默认也优先使用 `rg`。
- 已知关键 Python 函数后，需要理解上下游、影响范围或跨模块调用链时，使用 `codegraph_callers`、`codegraph_callees`、`codegraph_trace`。CodeGraph 结果必须结合局部源码或 `rg` 命中核验，不将静态调用图视为唯一事实来源。
- CodeGraph MCP 索引不可用时，先执行 `.\scripts\setup-codegraph.cmd`。Cursor 需要重启以加载项目 MCP；Codex App 还需要单独配置用户级 MCP 并重启。详细搜索策略见 `docs/25-codegraph-search-guide.md`。
- 本地启动、编译、测试、构建优先使用仓库 `scripts/` 目录下脚本，不要直接按个人习惯拼 `mvn` / `npm` 命令。
- Python 后端默认入口使用 `scripts/run-backend.cmd`；排查脚本行为或直连 Python 后端时再使用 `scripts/run-backend-python.cmd`。
- Python 测试优先使用 `scripts/run-backend.cmd test`，或按影响范围执行相关 pytest 文件。
- Java 后端脚本使用 `scripts/run-backend-java.cmd`；Java Maven 测试仅保留历史用途，默认不要运行。
- 前端启动使用 `scripts/run-frontend.cmd`；需要构建时使用 `scripts/run-frontend.cmd build`。
- 测试验证按影响范围选择最小集：前端样式/交互改动优先只跑前端 build；Python 局部后端改动优先跑相关 contract/unit 测试文件；只有改到主链路、共享模型、通知、数据库兼容或多模块交界时才跑全量 Python 测试。
- 只有脚本缺少所需能力或脚本本身失败且需要定位根因时，才直接进入 `backend-python/` 或 `frontend/` 执行底层命令，并在结论中说明原因。
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
- 至少有一个 `webhook/manual -> 分析 -> 提醒卡片 -> 通知 -> 落库` 的完整链路
- 如本次改动涉及 AI Review，至少有一个 `trigger -> provider execution -> result/progress -> 通知或前端可见` 的完整链路
- 有 demo 数据
- 有可用前端页面与必要配置入口
- README 写清启动方式与验证步骤
- 改动范围内有最小可复现验证步骤与对应测试
