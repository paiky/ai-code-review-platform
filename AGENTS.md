## Project

AI代码质量审查平台

## Product goal

构建可接入 GitLab、钉钉和多模型 Provider 的研发质量平台。输入 MR、Push、manual review、commit range
或 branch diff 后，先通过规则识别接口、数据库、缓存、MQ、配置等高价值变更并生成结构化提醒卡片，再按项目
或全局配置触发代码质量 AI Review。

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

### 实现、文档与阶段边界

- 以后端 Python 和 React 前端为默认维护范围；用户明确指定的任务范围优先。
- 以用户要求或已确认计划中的一个可验收目标为实施单元，不自行扩展到无关能力。
- 新功能、跨模块改造、接口或 schema 变化、部署与操作行为变化，应先更新对应专题设计或操作文档，再写代码。
  简单缺陷修复、内部重构、测试修复、文案或文档本身的修改，不强制新建计划文档。
- 涉及数据结构或接口契约时，先明确数据结构与接口，再实现业务逻辑。
- 多阶段推进计划必须为每个阶段写清目标、范围、非目标、验收方式、授权边界和停止点。只有用户需要跨任务复制
  或交接时，才附一段简短的阶段启动指令；不强制生成总控 Prompt 或逐阶段 Prompt，也不要重复计划正文。
- 后续新增或更新的专题计划文档，每个推进阶段（包括只有一个阶段的计划）都必须标注“改动量等级：小 / 中 / 大”，
  并用一句话说明判断依据。小表示单页面、单模块或局部内部调整且不改变公开契约；中表示跨多个组件或模块、存在显著
  交互或兼容验证，但不需要跨端数据迁移；大表示跨前后端/数据库/多服务，或涉及公开接口、schema、迁移、部署和高风险
  主链路。等级用于表达实施范围与验证复杂度，不等同于工时估算；阶段范围变化时必须同步复核并更新等级。
- 后续计划在规划阶段首次评估时，只要任一推进阶段的改动量等级为“大”，就必须在计划文档落地前继续拆分，不能保留
  单一“大”阶段等到实施前再复核。拆分后的每个子阶段都要重新标注改动量等级；仍为“大”时继续拆分，直到各阶段均为
  “小”或“中”。拆分必须按可独立验收、可独立授权且能够安全停留的交付边界进行，不得仅按文件数量机械拆分，也不得
  形成前端入口领先于 Backend 安全约束、接口领先于必要兼容保护或其它不可用的中间版本。
- 多阶段计划完成当前阶段后必须停止，汇报验证结果并等待用户确认，再进入下一阶段。
- `docs/36-review-platform-current-roadmap.md` 已冻结为历史路线归档，不再作为当前总控，也不登记新专项、阶段
  状态或实施结果。当前阶段以用户明确指定的专题文档及其停止点为准；历史计划中要求同步更新 `docs/36` 的
  文字视为过期约定。
- 只有项目定位、目录结构、默认启动入口、基础配置入口或文档路由变化时才更新 `README.md`。功能行为、阶段
  记录、接口语义和验收结果写入对应专题文档。
- 所有 PR / patch 的交付说明必须包含“改了什么、为什么、如何验证”。

### 启动、测试与验收

- 本地启动、测试和构建优先使用 `scripts/`：
  - Python 后端默认使用 `scripts/run-backend.cmd`；排查脚本或直连 Python 后端时使用
    `scripts/run-backend-python.cmd`。
  - Python 测试优先使用 `scripts/run-backend.cmd test`，或按影响范围执行相关 pytest 文件。
  - 前端使用 `scripts/run-frontend.cmd`；构建使用 `scripts/run-frontend.cmd build`。
  - `scripts/run-backend-java.cmd` 仅供用户明确要求的历史 Java 验证。
- 只有脚本缺少所需能力或脚本失败且需要定位根因时，才进入 `backend-python/` 或 `frontend/` 执行底层命令，
  并在结论中说明原因。
- 按影响范围选择最小充分验证：前端样式或交互改动优先运行前端测试 / build；Python 局部改动优先运行相关
  contract / unit 测试；只有主链路、共享模型、通知、数据库兼容或多模块交界变化时才考虑全量 Python 测试。
- 行为改动必须补对应测试。示例数据只在新增流程、schema、演示页面或可复现验收确有需要时补充。
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

- 改动范围能够本地运行，并有最小可复现验证步骤和对应测试。
- 修改 webhook、manual review、分析、提醒卡片、通知或落库主链路时，验证受影响链路能够闭环。
- 修改 AI Review 时，验证受影响的 trigger、provider execution、result / progress、通知或前端可见链路。
- 修改前端能力时，提供可用页面或交互，并完成与风险相称的测试、build 或浏览器验收。
- 修改启动、配置、部署、迁移或操作方式时，在对应专题文档中写清步骤；只有入口或文档路由变化时更新
  `README.md`。
- 新增流程、schema 或演示能力时，按验收需要补充示例数据。
