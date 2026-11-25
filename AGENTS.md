## Project

AI代码质量审查平台

## Product goal

构建可接入 GitLab、钉钉和多模型 Provider 的研发质量平台。输入 MR、Push、manual review、commit range
或 branch diff 后，先通过规则识别接口、数据库、缓存、MQ、配置等高价值变更并生成结构化提醒卡片。自动 AI Review
由全局能力开关、项目对应事件的触发策略和已启用的 Review Profile 共同决定。

当前交付主链路包括：

- GitLab webhook / manual review -> diff / changed files -> 规则分析 -> 提醒卡片 -> 通知与落库；
- AI Review trigger -> provider execution -> result / progress -> 钉钉通知或前端可见；
- 任务列表、任务详情、设置、版本更新等 React 前端能力；
- 本地启动、测试、迁移和 Docker 部署支持。

## Architecture and engineering constraints

- Active backend：Python FastAPI（`backend-python/`），运行时 Python 3.12+。
- Legacy backend：Java Spring Boot（`backend/`）只作历史参考；除非用户明确要求，不新增实现、测试或编译验证。
- Frontend：React + Ant Design（`frontend/`）。
- Database：MySQL。Redis 运行时依赖按功能可选；MQ 重点是变更分析和抽象，不默认引入重型运行基础设施。
- 数据库兼容：现有部署包含 MySQL 5.7，新增或修改 SQL 默认保留 5.7 兼容；使用窗口函数、CTE、`SKIP LOCKED`
  等版本专属能力时，须明确版本判断并保留兼容路径。涉及版本差异的排障，通过后端实际连接执行只读
  `SELECT VERSION()`，不以同机其它容器镜像或本地 MySQL 8 的验证结果代替。具体症状与处理见
  `docs/11-agent-environment-pitfalls.md` 的“数据库与迁移”。
- Integrations：GitLab API / webhook、DingTalk webhook、多模型 AI Review Provider。
- 设计保持模块化、配置优先和结构化输出；AI 是规则审查的增强，不是唯一依赖。
- 行为改动必须可测试；新增或变更的接口必须有清晰 DTO / VO / schema。

## Working style

### 阅读与检索

- 新对话默认只读取 `AGENTS.md`。不要默认通读 `README.md` 或批量读取 `docs/`；先根据当前任务使用 `rg`
  定位相关章节、代码和测试，再局部读取命中内容。
- 只有涉及启动、配置、部署、验证命令或项目入口说明时，才在 `README.md` 中检索并读取相关章节。
  README 中的文档导航只是任务路由，不代表必读清单。
- 在 Windows PowerShell 中阅读中文 Markdown / 文档时，优先使用
  `Get-Content -Raw -Encoding UTF8 <path>`，避免默认编码导致中文乱码。
- 搜索代码时使用 `rg` 并遵守根目录 `.rgignore`，不要绕过忽略规则扫描依赖、构建产物或缓存目录。
- 已知接口路径、字段名、错误信息、日志内容或目标字符串时，优先直接搜索该字符串。从业务问题排查 Python
  后端时，先定位候选模块和错误文案，再局部阅读真实调用链；已知关键函数后反查其调用者和测试影响范围。

### CodeGraph 使用边界

- 默认使用 `rg` 定位文件、符号、接口路径、字段、配置、日志、错误文案和前端代码；CodeGraph 不是任务开始、
  代码阅读或代码修改的固定前置步骤。
- 仅在已知关键符号且需要分析 callers、callees 或影响范围，需要追踪 Python 后端跨模块调用链，或 `rg` 与
  局部源码阅读不足以确定调用关系时使用 CodeGraph。
- 文档、配置、脚本、日志、环境问题、React 前端定位、已知字符串或文件路径、简单局部修改、测试修复和样式
  调整不调用 CodeGraph。
- 单个任务默认最多调用两次 CodeGraph；获得候选链路后转为阅读局部源码，不重复执行同类查询。
- CodeGraph 不可用、未配置、索引缺失或调用失败时，直接使用 `rg`；除非用户明确要求，不安装、初始化、同步、修复或重建
  CodeGraph。
- 除非当前任务就是 CodeGraph 维护或索引排障，不主动调用 `codegraph_status`、`init`、`sync` 或重建索引。

### 实现、文档与阶段边界

- 本项目的后端设计和接口文档按本文件及仓库专题文档约定编写，不使用 `backend-design-doc` 和 `backend-api-interface-doc` 技能。
- 以后端 Python 和 React 前端为默认维护范围；用户明确指定的任务范围优先。
- 以用户要求或已确认计划中的一个可验收目标为实施单元，不自行扩展到无关能力。
- 涉及业务规则、公开契约、数据迁移或部署方式变化时，先明确设计并更新相关文档；局部修改按任务检索相关章节。
  单纯文案、样式和不改变契约的修复，不强制新增设计文档。
- 涉及数据结构或接口契约时，先明确数据结构与接口，再实现业务逻辑。
- 多阶段推进计划必须为每个阶段写清目标、范围、非目标、验收方式、授权边界和停止点。只有用户需要跨任务复制
  或交接时，才附一段简短的阶段启动指令；不强制生成总控 Prompt 或逐阶段 Prompt，也不要重复计划正文。
- 后续新增或更新的专题计划文档，每个推进阶段（包括只有一个阶段的计划）都必须标注“改动量等级：小 / 中 / 大”，
  并用一句话说明判断依据。小表示单页面、单模块或局部内部调整且不改变公开契约；中表示跨多个组件或模块、存在显著
  交互或兼容验证，但不需要跨端数据迁移；大表示跨前后端/数据库/多服务，或涉及公开接口、schema、迁移、部署和高风险
  主链路。等级用于表达实施范围与验证复杂度，不等同于工时估算；阶段范围变化时必须同步复核并更新等级。
- 改动量等级用于表达范围与验证复杂度，不作为禁止实施的门槛。“大”阶段优先按可独立验收、可安全停留的边界拆分；
  无法继续安全拆分时，保留该阶段，并写明原因、验证和恢复方式。拆分后的子阶段重新标注改动量等级，不得仅按文件
  数量机械拆分，也不得形成前端入口领先于 Backend 安全约束、接口领先于必要兼容保护或其它不可用的中间版本。
- 用户已明确要求实现的任务，在授权范围内连续完成。多步骤任务可先简述计划，无需因此等待确认。仅在关键需求无法
  推断、需要扩大范围，或存在尚未授权的外部操作时请求确认。用户明确指定的阶段停止点必须遵守。
- `docs/36-review-platform-current-roadmap.md` 已冻结为历史路线归档，不再作为当前总控，也不登记新专项、阶段
  状态或实施结果。当前阶段以用户明确指定的专题文档及其停止点为准；历史计划中要求同步更新 `docs/36` 的
  文字视为过期约定。
- 只有项目定位、目录结构、默认启动入口、基础配置入口或文档路由变化时才更新 `README.md`。功能行为、阶段
  记录、接口语义和验收结果写入对应专题文档。
- 所有 PR / patch 的交付说明必须包含“改了什么、为什么、如何验证”。

### 启动、测试与验收

- 本地启动、测试和构建优先使用 `scripts/`；`scripts/` 只保留 PowerShell `.ps1`，后续不再新增 `.cmd`、`.mjs` 等其它脚本类型。
  Agent 或受执行策略限制的终端使用 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <script.ps1> ...` 调用，不要求永久修改系统执行策略：
  - Python 后端统一使用 `scripts/run-backend.ps1`。
  - Python 测试优先使用 `scripts/run-backend.ps1 test`，或按影响范围执行相关 pytest 文件。
  - 前端使用 `scripts/run-frontend.ps1`；构建使用 `scripts/run-frontend.ps1 build`。
- 只有脚本缺少所需能力或脚本失败且需要定位根因时，才进入 `backend-python/` 或 `frontend/` 执行底层命令，
  并在结论中说明原因。
- 仅当用户在当前任务明确要求单元测试时，才新增、修改或运行单元测试。全量测试命令包含单元测试，适用同一约束。
- 按影响范围选择最小充分验证。前端样式或交互改动优先考虑 build 或浏览器验收，Python 局部改动优先考虑聚焦静态检查、
  人工核验或适用的契约验证。交付时说明实际验证方式及是否运行单元测试。
- 示例数据只在新增流程、schema、演示页面或可复现验收确有需要时补充。
- 启动 Vite、FastAPI、Worker、watcher 或 mock 等长驻服务前，先检查目标端口和 HTTP health / 页面；已有可用
  服务时直接复用。新启动服务必须使用有界 ready 检查，分别确认进程或端口 owner、端口监听和 HTTP 响应，
  不等待长驻进程退出。验收结束只停止本次明确启动且仍拥有目标端口的 PID。
- Windows / Codex 下若启动命令无法在服务 ready 后有界返回，不继续叠加 detached 包装；改由用户终端或独立
  runner 持有服务，Agent 只做 health check 和验收。详细处理方式按需查看
  `docs/11-agent-environment-pitfalls.md` 的对应章节。

### 问题记录

- 遇到环境、脚本、部署、Codex、检索或工具链问题时，先用 `rg` 在
  `docs/11-agent-environment-pitfalls.md` 中搜索症状或关键词，只读取命中章节。
- 新解决且可复用的环境、工具、部署、Codex 或检索类踩坑，补充到
  `docs/11-agent-environment-pitfalls.md`；一次性环境现象不登记。
- 业务规则误判、接口语义和产品行为问题优先写入对应专题文档。只有没有合适专题且值得长期回归的真实 BUG
  才写入 `docs/24-bug-log.md`，不要重复维护两份记录。

## Definition of done

- 改动范围能够本地运行，并有最小可复现验证步骤。单元测试按上面的授权规则执行。
- 修改 webhook、manual review、分析、提醒卡片、通知或落库主链路时，验证受影响链路能够闭环。
- 修改 AI Review 时，验证受影响的 trigger、provider execution、result / progress、通知或前端可见链路。
- 修改前端能力时，提供可用页面或交互，并完成与风险相称的测试、build 或浏览器验收。
- 修改启动、配置、部署、迁移或操作方式时，在对应专题文档中写清步骤；只有入口或文档路由变化时更新
  `README.md`。
- 新增流程、schema 或演示能力时，按验收需要补充示例数据。
