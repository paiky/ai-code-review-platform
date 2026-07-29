# Agent Review 进度动画风格扩展计划

## 1. 状态与结论

- 文档状态：计划已确认，等待 `docs/48` 三阶段完成后实施。
- 前置专项：`docs/48-review-task-detail-unified-progress-ui-plan.md`。
- 结论：保留第一版大脑动画并扩展能量球和 Lottie 是可行的；三种风格必须共享同一状态语义和无障碍
  契约，只改变表现，不改变 ReviewJourney、轮询、时间轴或 Review 结果。
- 本文只规划动画扩展，不在计划阶段修改前端代码、依赖或资源。

固定交付顺序：

```text
docs/48：可插拔 AgentReviewAnimation + BRAIN 默认风格
  -> docs/49 阶段一：ENERGY + 两项切换 + 浏览器偏好
  -> 用户验证
  -> docs/49 阶段二：本地 LOTTIE + 三项切换 + 按需加载
```

## 2. 目标与非目标

### 2.1 目标

- 第一版 `BRAIN` 永远保留为默认和故障兜底。
- 增加零依赖 `ENERGY` 风格。
- 在独立阶段增加本地打包、按需加载的 `LOTTIE` 风格。
- Agent Review Hero 提供紧凑下拉按钮切换风格。
- 同一浏览器记住用户选择，不新增平台设置或后端接口。
- 三种风格表达相同的排队、分析、取证、收敛、提交和终态语义。
- 动画加载、渲染、存储或资源失败不得影响 Review 主结果和页面轮询。

### 2.2 非目标

- 不给 Standard Review 提供风格切换；Standard 保持 `docs/48` 的固定 Provider 动效。
- 不允许远程 Lottie URL、运行时下载或运营后台上传动画。
- 不用动画表现 token、推理链、置信度、预计剩余时间或虚构完成百分比。
- 不新增数据库、公开 API、用户账号偏好字段或服务端配置。
- 不改变 ReviewJourney 阶段、Agent trace、fallback、Provider、Prompt、预算或安全白名单。
- 不删除大脑动画，不把 Lottie 设为默认。
- 不在同一阶段同时实现 ENERGY 和 LOTTIE。

## 3. 统一动画契约

### 3.1 风格枚举

内部枚举固定为：

```text
BRAIN
ENERGY
LOTTIE
```

未知、空、损坏或当前不可用的值统一解析为 `BRAIN`。

### 3.2 组件输入

`AgentReviewAnimation` 只接收纯展示输入：

```text
style
reviewState
agentPhase
reducedMotion
ariaLabel
compact
```

其中：

- `reviewState`：`QUEUED / RUNNING / SUCCESS / FALLBACK / FAILED / CANCELLED`。
- `agentPhase`：`WAITING / ANALYZING / EVIDENCE / CONVERGING / SUBMITTING / TERMINAL`。
- `reducedMotion`：来自系统媒体查询，优先于用户风格选择。
- `compact`：用于终态紧凑 Hero，不改变状态语义。

动画组件不得直接读取 Review API、progress、Worker、Provider 或路由数据；状态归一化继续由
`docs/48` 的 ReviewJourney 层负责。

### 3.3 注册表

使用固定注册表隔离风格：

```text
style
label
description
renderer
lazy
available
fallbackStyle
```

固定规则：

- `BRAIN`：同步、始终可用、`fallbackStyle=BRAIN`。
- `ENERGY`：同步、始终可用、`fallbackStyle=BRAIN`。
- `LOTTIE`：异步、通过动态 import 可用、`fallbackStyle=BRAIN`。
- 注册表只包含代码内固定枚举，不接受后端或 URL 动态注册。
- 切换菜单只显示当前版本已交付且可选择的风格。

### 3.4 错误边界

- 每个风格渲染器使用局部错误边界，不能让整个任务详情白屏。
- ENERGY 失败：当前 Hero 立即回退 BRAIN。
- LOTTIE chunk、资源或播放器失败：本次会话标记 LOTTIE 不可用并回退 BRAIN。
- LOTTIE 失败不覆盖用户持久化偏好，下一次完整页面加载允许重试。
- 降级只以固定的非阻断 `aria-live=polite` 文案说明，不展示异常对象、URL 或堆栈。
- 动画失败不写 Review progress、不调用通知、不改变轮询或 Review 状态。

## 4. 状态与视觉语义

三种风格使用同一状态表：

| Review / Agent 状态 | BRAIN | ENERGY | LOTTIE |
| --- | --- | --- | --- |
| 排队 | 静态轮廓和低频呼吸 | 缓慢光环 | 低动态等待循环 |
| 分析变更 | 神经节点扩散 | 核心向外脉冲 | 通用思考循环 |
| 受控取证 | 连线定向流动 | 轨道粒子移动 | 通用思考循环 |
| 收敛结论 | 脉冲向中心收拢 | 能量核心收缩 | 降低动态强度 |
| 提交结果 | 节点向结果图标汇聚 | 定向光束 | 提交过渡或通用循环 |
| 成功 | 静态成功覆盖层 | 同左 | 同左 |
| fallback | 橙色转交覆盖层 | 同左 | 同左 |
| 失败 | 静态错误覆盖层 | 同左 | 同左 |
| 取消 | 灰色取消覆盖层 | 同左 | 同左 |

具体阶段仍由 Hero 文字和统一时间轴表达。动画只传达“仍在运行”和相对状态变化，不声称呈现模型真实思考。

## 5. BRAIN 基线

`BRAIN` 由 `docs/48` 阶段二交付：

- 原生 SVG + CSS；
- 第一版默认风格；
- 始终同步可用；
- 不依赖资源文件或播放器；
- 作为 ENERGY / LOTTIE 的错误兜底；
- 终态覆盖层由公共组件提供，避免三种风格重复实现成功、失败、fallback 和取消。

`docs/49` 不重画或删除 BRAIN，只允许为了统一契约做无行为变化的抽取。

## 6. ENERGY 风格

### 6.1 视觉组成

- 中央能量核心；
- 两条以内的抽象轨道；
- 少量受控粒子；
- 外圈柔和光晕；
- 不使用 Canvas、WebGL、图片或第三方动画库。

### 6.2 动画限制

- 只使用 SVG 和 CSS transform / opacity；
- 同时活动粒子不超过 12 个；
- 不使用高频闪烁、快速缩放或大面积饱和发光；
- 不依赖随机数，避免轮询重新渲染产生视觉跳变；
- 页面不可见时暂停 CSS 动画；
- reduced-motion 下只保留静态核心、轨道和状态覆盖层。

### 6.3 状态映射

- 排队：光环慢速呼吸，粒子静止。
- 分析：核心低频向外脉冲。
- 取证：粒子沿轨道单向移动。
- 收敛：轨道亮度下降，粒子向核心靠拢。
- 提交：核心向终态图标产生一次定向光束。
- 终态：停止循环，使用公共覆盖层。

## 7. LOTTIE 风格

### 7.1 播放器

- 采用官方 `@lottiefiles/dotlottie-react`。
- 只在用户选择 `LOTTIE` 时通过动态 import 加载。
- 资源使用本地 `.lottie` 或 JSON 文件，随 Vite 构建产物发布。
- 官方 React 播放器和格式能力参考：
  `https://docs.lottiefiles.com/en/runtimes/distributions/react`。

### 7.2 首版资源

首版只交付一个通用 Agent 运行中动画：

- 用于排队和所有非终态 Agent 子阶段；
- 阶段差异继续由 Hero 文案、状态 Tag 和时间轴表达；
- 允许按阶段调整播放/暂停或速度，但不得因资源缺少 marker 伪造阶段；
- 成功、失败、fallback 和取消统一使用公共静态覆盖层。

### 7.3 本地资源边界

- 禁止远程 URL和运行时下载。
- 禁止音频、外部字体、外部图片、外部脚本和未审核表达式。
- 只允许矢量图层；如确需内嵌位图必须停止并重新评估。
- 单资源原始大小不超过 300 KB。
- 动画时长建议 2～4 秒循环，帧率不超过 60 fps。
- 资源必须为项目自产或具有可随产品分发的明确许可证。
- 第三方资源必须在同目录保存来源、作者、许可证和修改说明。
- 最终包不得包含设计源文件、账号信息或外部资源 token。

### 7.4 生命周期

- 组件挂载且页面可见时才播放。
- 浏览器标签隐藏时暂停。
- reduced-motion 时停在安全静态帧。
- 切换到 BRAIN / ENERGY、组件卸载或 Review 进入终态时暂停并销毁播放器。
- 轮询只更新文字或阶段时不得重建播放器。
- 同一 Hero 同时最多存在一个 Lottie 播放实例。

### 7.5 加载与回退

```text
用户选择 LOTTIE
  -> 动态加载播放器 chunk
  -> 加载本地动画资源
  -> 成功：播放
  -> 失败：当前会话回退 BRAIN
```

- 加载期间显示 BRAIN 静态占位，避免 Hero 抖动。
- 不展示网络重试按钮；完整页面重载会自然重试。
- LOTTIE 不可用时菜单保留已选标记并提示“本次会话已回退大脑动画”。
- 资源失败不得触发 Review error Alert。

## 8. 风格切换与偏好

### 8.1 切换入口

- 仅 Agent Review Hero 右上角显示紧凑“动画风格”按钮。
- 使用图标 + 可访问名称打开下拉菜单。
- 阶段一菜单项：`大脑 / 能量球`。
- 阶段二菜单项：`大脑 / 能量球 / Lottie`。
- 当前风格显示选中标记和简短说明。
- 390px 窄屏按钮保持图标和短标签，不展示三项横向 Segmented。
- Standard Review 不显示该按钮。

### 8.2 持久化

固定 storage key：

```text
ai-code-review.agentAnimationStyle.v1
```

固定规则：

- 只保存 `BRAIN / ENERGY / LOTTIE` 字符串。
- 第一次使用或 key 不存在时为 `BRAIN`。
- 非法值、JSON 污染或读取异常回退 `BRAIN`。
- 写入失败时仅保留当前组件内选择，不显示阻断错误。
- 偏好在同一浏览器的不同任务间共享，不同步到账号或服务器。
- 阶段一读到未来的 `LOTTIE` 值时回退 BRAIN，但不显示不存在的菜单项。

### 8.3 reduced-motion

- `prefers-reduced-motion: reduce` 的行为优先于风格偏好。
- 保留用户选择，渲染对应静态插画。
- 菜单继续允许切换，并提示“系统已启用减少动态效果”。
- 不因 reduced-motion 自动改写 localStorage。

## 9. 性能与离线部署

- BRAIN / ENERGY 与 Hero 主代码同步打包。
- LOTTIE 播放器和资源必须独立动态 chunk。
- 默认 BRAIN 首屏不得请求 LOTTIE chunk 或资源。
- 引入风格注册表和切换按钮后，主 chunk gzip 增量上限为 20 KB。
- LOTTIE 资源只从当前站点构建产物加载，不产生外部网络请求。
- 轮询期间播放器实例数保持 1，不累积 Canvas、监听器、定时器或 `requestAnimationFrame`。
- Docker 离线包继续由现有 frontend 镜像携带全部资源，不新增服务器文件分发步骤。
- 离线环境禁网时三种风格都必须可用。

## 10. 无障碍与安全

### 10.1 无障碍

- 切换按钮和菜单支持 Tab、Enter、Space、Escape 和焦点返回。
- 动画容器提供随 Journey 更新的 `aria-label`。
- 风格切换结果使用 `aria-live=polite`，不得重复播报每次心跳。
- 状态同时使用文字、图标和颜色。
- 动画不获取焦点、不播放声音、不制造不可停止的高频闪烁。

### 10.2 安全

- 动画组件不接收或渲染 progress detail、Prompt、查询、工具参数、源码、diff、路径、模型原文或推理。
- Lottie 资源不包含外部 URL、音频、脚本、认证信息或用户数据。
- 不从 CDN、LottieFiles 市场或其它第三方域名在运行时拉取资源。
- 播放器错误只输出固定 UI 文案，不把异常正文送入 Review progress 或通知。
- 动画偏好不是安全配置，不得影响 Agent 启用、Provider、预算或工具白名单。

## 11. 实施范围

预期前端改动：

- `AgentReviewAnimation` 契约和风格注册表；
- ENERGY SVG/CSS 组件；
- 动画偏好纯函数与 Hero 下拉菜单；
- 阶段二的 Lottie 懒加载边界、本地资源和许可证记录；
- 对应纯函数测试、浏览器验证和本文实施结果。

允许阶段二新增：

- `@lottiefiles/dotlottie-react`；
- 一个审核后的本地 `.lottie` 或 JSON 资源；
- 必要的资源许可证说明。

不得修改：

- Java 或 Python Backend；
- 数据库或 API；
- ReviewJourney 状态和事件映射；
- Standard Review、fallback、Agent trace、Provider、Prompt、预算、工具白名单和 Review Card schema；
- Compose、Docker 部署流程或远程运行环境。

## 12. 阶段一：动画契约与能量球

### 12.1 前置条件

- `docs/48` 三阶段均完成并由用户验收。
- BRAIN 动画、Hero、时间轴、Drawer 和 reduced-motion 已稳定。
- 工作区不得混有未提交的 `docs/48` 阶段代码。

### 12.2 实施内容

- 从现有 BRAIN 实现抽取固定注册表和 `AgentReviewAnimation` 边界，不改变大脑视觉。
- 新增 ENERGY SVG/CSS 实现。
- 新增 localStorage 偏好纯函数。
- Agent Hero 增加“大脑 / 能量球”下拉菜单。
- Standard Hero 不显示切换入口。
- 完成错误边界、页面可见性暂停和 reduced-motion。
- 不安装 Lottie 依赖，不增加 LOTTIE 菜单项。

### 12.3 测试

- BRAIN 默认和未知值回退；
- ENERGY 各状态映射；
- localStorage 首次、有效、非法、读取失败和写入失败；
- 跨任务偏好复用；
- Standard 不显示切换；
- 轮询不重建动画；
- 页面隐藏暂停、卸载清理和 reduced-motion；
- 1440 / 1024 / 390 视觉、键盘和焦点；
- 全部前端纯函数测试和 production build。

### 12.4 停止点

完成后回填本文阶段一结果并停止。用户确认大脑、能量球、切换密度和性能后，才允许进入阶段二。

## 13. 阶段二：本地 Lottie 风格

### 13.1 前置条件

- 用户明确确认阶段一。
- ENERGY 与偏好切换已部署验证。
- 已确定本地动画资源、许可证和资源审计结果。

### 13.2 实施内容

- 安装官方 dotLottie React 播放器。
- 添加一个本地审核资源和许可证说明。
- 增加 LOTTIE 懒加载渲染器和第三个菜单项。
- 完成 loading 占位、失败回退、页面隐藏暂停和实例销毁。
- 验证默认 BRAIN 不加载 Lottie chunk。
- 验证 Docker 离线部署不产生外部请求。
- 默认风格继续为 BRAIN。

### 13.3 测试

- 播放器 chunk 按需加载；
- 本地资源成功、损坏、缺失和 chunk 失败；
- 失败后当前会话回退 BRAIN，持久化偏好不被覆盖；
- 切换风格和卸载时播放器销毁；
- 轮询不重建实例；
- reduced-motion 静态帧；
- 标签页隐藏暂停和恢复；
- 许可证、300 KB 上限、外部 URL/音频/字体/图片/表达式审计；
- 主 chunk gzip 增量不超过 20 KB；
- 禁网浏览器验证、全部前端测试和 production build。

### 13.4 停止点

完成后回填本文阶段二结果并停止，等待用户确认部署。不得自动把 LOTTIE 设为默认，不得继续引入更多风格。

## 14. 验收矩阵

| 场景 | 期望 |
| --- | --- |
| 首次进入 Agent Review | 默认 BRAIN |
| 选择 ENERGY 后打开其它任务 | 同一浏览器继续 ENERGY |
| localStorage 损坏 | 安全回退 BRAIN |
| Standard Review | 无风格切换按钮 |
| reduced-motion | 保留所选静态插画，无循环运动 |
| Agent fallback | 所有风格显示公共橙色转交覆盖层 |
| LOTTIE 首次选择 | 按需加载本地 chunk 和资源 |
| LOTTIE 加载失败 | 当前会话回退 BRAIN，Review 不受影响 |
| 轮询刷新 | 动画不重新开始，播放器不增加 |
| 浏览器标签隐藏 | 动画暂停 |
| Docker 离线环境 | 无外部请求，三种风格可用 |
| 390px | 下拉按钮不挤压状态和阶段文案 |

## 15. 文档与提交边界

- 阶段一开始前先更新本文状态为“阶段一实施中”，完成后回填结果、测试和风险。
- 阶段二同样先更新状态再实施。
- 每个阶段只提交本阶段相关前端、资源、测试和本文。
- 不把 `docs/48` 的未提交代码、其它功能或用户文件混入动画提交。
- 每阶段完成后必须停止等待用户确认，不自动提交、推送或部署。

## 16. 总控 Prompt

```text
请只按 docs/49-review-progress-animation-style-extension-plan.md 推进 Agent Review 动画风格扩展。

开始前阅读根目录 AGENTS.md、docs/48、docs/49 和现有 Review Hero、ReviewJourney、动画、样式及测试。
确认 docs/48 三阶段已完成并由用户验收；如果前置未完成或工作区混有未提交的上一阶段代码，停止报告。

每次只实施 docs/49 的一个阶段。允许修改现有 React 前端、动画组件、样式、前端测试、阶段二必要的
本地动画资源和 docs/49；不得修改 Java/Python Backend、数据库、API、ReviewJourney 状态、Standard
Review、fallback、Agent trace、Provider、Prompt、预算、工具白名单、Review Card schema、Compose 或部署流程。

BRAIN 永远是默认和故障兜底。动画只表达运行状态，不展示或模拟模型推理，不影响轮询和 Review 主结果。
不得运行时访问远程动画 URL。

阶段完成后执行全部前端纯函数测试、scripts\run-frontend.cmd build、响应式/无障碍/性能/离线检查，
回填 docs/49 并停止，等待用户确认。未经确认不得进入下一阶段、提交、推送、部署或执行真实 Agent Review。
```

## 17. 阶段一 Prompt

```text
请只实施 docs/49 的阶段一“动画契约与能量球”。

前置：
1. 阅读 AGENTS.md、docs/48、docs/49。
2. 确认 docs/48 三阶段已完成、BRAIN Hero 已验收且阶段代码已提交。
3. 检查 git status，保留用户修改；上一阶段未提交则停止。

目标：
1. 从现有 BRAIN 抽取可插拔 AgentReviewAnimation 契约和固定风格注册表。
2. BRAIN 视觉、默认行为和故障兜底保持不变。
3. 新增零依赖 ENERGY SVG/CSS 风格，覆盖排队、分析、取证、收敛、提交和公共终态覆盖层。
4. 新增 ai-code-review.agentAnimationStyle.v1 偏好，只接受 BRAIN/ENERGY/LOTTIE；本阶段 LOTTIE
   解析为 BRAIN 且不显示菜单项。
5. Agent Hero 增加紧凑“大脑/能量球”下拉按钮；Standard 不显示。
6. 支持页面隐藏暂停、卸载清理、轮询不重置、键盘、焦点和 reduced-motion。

边界：
- 不安装 Lottie 依赖，不添加 Lottie 资源或菜单项。
- 不修改 Backend、API、ReviewJourney、fallback 或 Review 结果。
- 不伪造进度，不展示模型推理。

测试：
- 注册表、偏好、错误回退、所有状态、Standard 隐藏、轮询稳定、页面可见性和 reduced-motion；
- 1440/1024/390 浏览器检查；
- 全部前端测试和 scripts\run-frontend.cmd build。

完成后回填 docs/49 阶段一结果并停止，等待用户确认阶段二；不得提交、推送或部署。
```

## 18. 阶段二 Prompt

```text
仅在用户确认阶段一后实施 docs/49 的阶段二“本地 Lottie 风格”。

前置：
1. 确认阶段一已部署验证并提交。
2. 明确本地动画资源、许可证、大小和安全审计结果。
3. 工作区混有阶段一未提交代码时停止。

目标：
1. 安装官方 @lottiefiles/dotlottie-react。
2. 添加一个不超过 300 KB、无远程 URL/音频/外部字体/外部图片/未审核表达式的本地动画资源和许可证说明。
3. 通过动态 import 增加 LOTTIE 渲染器，默认 BRAIN 不加载播放器 chunk。
4. 菜单扩展为大脑/能量球/Lottie，偏好继续使用现有 storage key。
5. 完成加载占位、失败回退、页面隐藏暂停、切换/卸载销毁、轮询不重建和 reduced-motion 静态帧。
6. Docker 离线环境不得产生外部资源请求。

边界：
- 默认仍为 BRAIN，不删除 BRAIN/ENERGY。
- 不新增远程动画管理、Backend 配置、上传入口或其它风格。
- 动画失败不得改变 Review 主结果。

测试：
- 动态 chunk、资源成功/失败、当前会话回退、偏好保留、实例销毁、后台暂停、轮询稳定；
- 许可证和资源安全审计；
- 主 chunk gzip 增量不超过 20 KB；
- 禁网浏览器、1440/1024/390、键盘和 reduced-motion；
- 全部前端测试和 scripts\run-frontend.cmd build。

完成后回填 docs/49 并停止等待部署确认；不得自动提交、推送、部署或继续增加动画风格。
```
