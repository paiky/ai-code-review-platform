# AI Review 配置入口合并计划

## 1. 状态与背景

- 计划状态：**阶段一已完成，等待阶段二确认（2026-08-13）**；
- 当前进度：阶段一已完成实现、自动化、构建和浏览器验收；阶段二未开始；
- 当前停止点：阶段一验收后，等待用户明确确认是否启动阶段二；
- 历史基线：传统后台壳层、模型连接与 Review 工作台、Agent 执行预算和 Standard Provider 默认可用等既有实现记录见
  [`docs/54-traditional-admin-shell-layout-plan.md`](54-traditional-admin-shell-layout-plan.md)。

当前设置侧边栏分别提供“AI Review 配置”和“模型连接与 Review 配置”。两个入口分别承载策略与 Prompt、模型与运行配置，
但同属 AI Review 管理域。为减少菜单认知成本，本计划将其合并为一个侧边栏入口，并使用 URL 联动页签区分两个独立配置域。

## 2. 已确认产品决策

- 设置侧边栏将现有“AI Review 配置”和“模型连接与 Review 配置”合并为一个“AI Review 配置”入口；
- 合并页使用两个 URL 联动页签：“模型与运行”和“策略与 Prompt”；
- “模型与运行”作为默认页签，继续承载 Agent / Standard 运行摘要、连接目录与详情、模型连接生命周期和 Agent 执行预算；
- “策略与 Prompt”继续承载项目组 AI Review 通用策略、Standard Review Profile、Provider / 模型覆盖、Prompt 编辑与预览；
- 两个页签保持独立保存，不新增跨接口“全部保存”；页面只合并信息架构，不合并 Agent Settings、Standard Provider、
  Profile 或项目组策略的 Backend 契约。

采用以下 canonical 路由：

- `/settings/ai-review/models`：模型与运行；
- `/settings/ai-review/policies`：策略与 Prompt；
- `/settings` 与 `/settings/ai-review`：replace 到 `/settings/ai-review/models`；
- `/settings/model-connections`：兼容 replace 到 `/settings/ai-review/models`；
- `/settings/review-profiles`：兼容 replace 到 `/settings/ai-review/policies`。

## 3. 阶段一：统一入口与路由契约

改动量等级：**中**。涉及设置导航模型、canonical / legacy 路由、浏览器历史和两个既有 dirty 域的页签切换保护，但不搬动
业务表单或改变保存接口。

前置条件：用户明确授权启动阶段一。

目标：先建立可独立验收的单入口、双页签路由骨架，使新旧地址、侧边栏选中态、刷新和历史导航都稳定可用；两个页签
暂时直接复用既有模块内容和样式。

范围：

- 设置侧边栏从四个子项收敛为“项目组 / 端类型配置、AI Review 配置、全局设置”三个子项；
- 为“AI Review 配置”增加页签元数据和统一父级选中键，两个 canonical 子路由在侧边栏保持同一菜单高亮；
- `/settings`、`/settings/ai-review` 和两个 legacy URL 按第 2 节执行 replace，避免重复历史记录；
- 页签点击使用路由导航，刷新、地址直达、前进、后退均还原正确页签；
- 保留现有 `review-model-settings:*`、`profile-settings:*` dirty token，不做无收益重命名；页签切换、侧边栏切换和历史导航
  分别检查当前页签所属 dirty 域，模型连接草稿继续额外检查 `dirtyReviewConnectionId`；
- 更新设置导航与 dirty 契约测试，覆盖新 canonical 路由、旧路由兼容、统一菜单选中和两域互不串线。

非目标：本阶段不调整两个模块的标题、字段、布局、请求、保存按钮或响应式样式；不删除旧路由兼容；不修改 Backend、
数据库、API、schema、README、`docs/36` 或 54 号历史实施正文。

验收方式：

- 三个设置菜单项顺序和高亮正确；两个 AI Review 子路由只高亮同一个侧边栏入口；
- 六类入口（`/settings`、父路由、两个 canonical 路由、两个 legacy 路由）均得到确定页面且不会形成重定向循环；
- 页签点击、刷新、前进、后退、一级菜单离开分别覆盖无 dirty、取消丢弃、确认丢弃和保存后直接离开；
- 设置导航定向测试、模型工作台既有契约测试、全部前端测试和前端 build 通过。

授权边界与停止点：阶段一只允许修改本文、前端设置导航/路由、统一页签骨架和对应测试；不得借机调整业务字段、接口、
视觉布局或 Backend。阶段一完成验证并回填结果后必须停止，等待用户确认再进入阶段二；不自动提交、推送或部署。

### 3.1 实施结果

- 设置侧边栏已从四个子项收敛为“项目组 / 端类型配置、AI Review 配置、全局设置”三个子项；“AI Review 配置”菜单
  默认进入 `/settings/ai-review/models`；
- 已建立“模型与运行 / 策略与 Prompt”两个 URL 页签；两个 canonical 路由共享同一个侧边栏选中键，并继续分别映射到
  `review-model-settings` 与 `profile-settings` 既有内容和 dirty token，不搬动业务表单；
- `/settings`、`/settings/ai-review`、`/settings/model-connections` 与 `/settings/review-profiles` 已使用 replace 收敛到
  对应 canonical 路由，未知设置子路由继续回到默认模型页；
- 页签切换统一经过现有设置导航守卫；模型连接草稿继续额外检查 `dirtyReviewConnectionId`，两个配置域没有合并保存或
  dirty 状态；
- 定向导航与壳层测试 `8/8` 通过；全部前端测试 `229/229` 通过；
- `scripts/run-frontend.ps1 build` 通过，Vite 完成 `3552` 个模块转换，仅有既有大 chunk 提示；
- 浏览器验证通过：三个设置菜单项与统一高亮正确；两个页签点击、刷新、前进、后退均恢复正确 URL 与页签；设置根路由、
  父路由和两个 legacy URL 均跳转正确；模型与策略两个域的临时草稿分别验证了“取消后留在原页”和“确认后丢弃并切换”；
  验收未保存任何配置、未修改 Key、未测试连接或调用真实 Provider；当前 `2020px` 视口无页面横向溢出。

## 4. 阶段二：内容归位与页面收敛

改动量等级：**中**。在统一页面内重组两个成熟模块，需处理重复标题、较长内容、条件区块、移动端页签和保存职责表达，
但继续复用现有组件状态与公开契约。

前置条件：阶段一已经完成、验证、回填实施结果并经用户确认；未确认不得提前实施阶段二。

目标：将两个既有模块收敛为一个清晰的“AI Review 配置”页面，保证用户能区分运行连接、项目策略和 Standard Prompt，
同时避免把两个页面简单上下拼接成约 2300px 的长表单。

范围：

- 页面只保留一个“AI Review 配置”主标题和简短说明，页签紧随标题；非活动页签不渲染业务面板，避免重复操作入口；
- “模型与运行”完整复用当前模型工作台层级：全局 Agent 开关、双运行摘要、连接目录/详情和 Agent 执行预算；
- “策略与 Prompt”按“项目组 AI Review 通用策略 -> Standard Review Prompt”顺序复用现有两个设置区；
- 将“Provider 覆盖”文案收敛为“Standard Provider 覆盖（可选）”，并说明留空时沿用 Standard 当前连接，避免与默认
  Provider 设置混淆；“模型覆盖”继续只作用于当前 Profile；
- 保留每个区域原有保存、恢复默认、预览、测试、清除 Key、新增/删除连接和设为当前行为，不增加跨域提交；
- 桌面页签保持紧凑横向排列；移动端允许等宽或横向滚动，但不得截断标题、遮挡操作或造成页面横向溢出；
- 更新模型工作台、Profile / 项目组策略、设置导航、样式与安全 mock 测试，并回填本节实施结果。

非目标：不把策略和 Prompt 塞入模型详情右栏；不把两个模块直接上下同时渲染；不改变 Agent / Standard 可用性、预算、
Profile 继承、项目组触发策略、Key、Provider 覆盖优先级或任何 Backend 行为；不执行真实 Review 或真实 Provider 测试。

验收方式：

- 两个页签各自只显示所属内容，页面没有重复主标题、重复全局开关或“全部保存”；
- 模型连接编辑、dirty 切换、新增/删除、测试、Key 清除、设为当前和预算保存不回归；
- 项目组选择、三个策略开关、Push 条件区、Profile 切换、Provider / 模型覆盖、Prompt 编辑/预览/恢复/保存不回归；
- `1440px`、`1024px`、`390px` 浏览器验收覆盖页签、长内容、条件区展开、操作区和无横向溢出；浏览器只使用固定安全
  mock 或只读现有数据，不写入真实 Key、不请求真实 Provider；
- 相关定向测试、全部前端测试和 `scripts/run-frontend.ps1 build` 通过，仅允许既有大 chunk 提示。

授权边界与停止点：阶段二只允许修改本文、前端 AI Review 合并页、局部样式、安全 mock 和对应测试；不得修改 Backend、
数据库、API、schema、README、`docs/36` 或 54 号历史实施正文。完成完整验证和结果回填后停止；不自动提交、推送或部署。

## 5. 风险与回退边界

- 主要风险是合并菜单后把“运行连接”和“审查策略”误解为同一保存域；通过 URL 页签、独立操作区和无“全部保存”控制；
- 旧收藏、文档和浏览器历史可能仍指向现有两个 URL；必须保留 replace 兼容，不做直接 404 或默认吞并到错误页签；
- dirty 风险集中在跨页签和历史导航；保持原 token 并按当前页签判定，比合并 token 更容易回归和回退；
- 若阶段二视觉收敛出现问题，可以保留阶段一的单入口与双路由骨架，仅回退内容样式，不影响旧路由、接口和数据；
- 本计划两个阶段均为“中”，不存在需要继续拆分的“大”阶段。

## 6. 推进记录

- 2026-08-13：确认合并菜单名称为“AI Review 配置”，页签名称为“模型与运行 / 策略与 Prompt”；
- 2026-08-13：完成两阶段计划，两个阶段改动量等级均为“中”，计划待实施；
- 2026-08-13：计划从 54 号历史实施文档迁移到本专题，后续只在本文件维护实施状态和验证结果。
- 2026-08-13：用户确认启动阶段一；阶段一进入实施中，阶段二仍未授权。
- 2026-08-13：阶段一完成。统一菜单、canonical / legacy 路由、URL 页签和原 dirty 保护已落地；定向测试 `8/8`、全部
  前端测试 `229/229`、生产构建和浏览器验收通过，按停止点等待阶段二确认。
