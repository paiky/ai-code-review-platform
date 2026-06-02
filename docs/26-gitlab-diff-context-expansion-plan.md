# GitLab 风格 Diff 上下文展开实施计划

## 状态

已完成。阶段 1、阶段 2、阶段 3 均已落地并完成影响范围内验证。

后续真实联调发现模型生成 Patch 可能与当前源码基线不一致。普通“查看 Diff”继续保留完整上下文展开；
AI 修复 Patch 预览已收口为紧凑展示，不再提供“展开上下文”入口，避免不稳定交互。

## 目标

让任务详情中的“查看 Diff”支持按需展开完整源码上下文，并让“查看 Diff”和“AI 修复 Patch 预览”
统一使用可切换明亮 / 暗黑主题的语法高亮代码视图。

完整上下文来自 GitLab Repository Files API。平台不在打开弹窗时立即拉取源码，只在用户点击展开入口后按任务、文件和版本读取。

## 总控 Prompt

```text
按本计划分阶段实现 GitLab 风格 Diff 上下文展开。每次只执行当前阶段：
1. 先更新 README、API 契约和必要文档。
2. 再实现当前阶段代码与最小测试。
3. 使用仓库 scripts/ 下脚本完成影响范围内验证。
4. 输出改了什么、为什么、如何验证。
5. 完成当前阶段后立即停止，等待用户验证并明确回复“继续下一阶段”。

禁止在未获得用户确认时提前进入后续阶段。禁止修改停止维护的 backend/ Java 后端。
```

## 阶段 1：后端上下文读取能力

### 阶段 Prompt

```text
实现 GitLab raw file 上下文接口。新增 GET /api/review-tasks/{taskId}/diff-context，
仅允许读取任务 changedFilesSummary 中已有路径。Push 使用 beforeSha / afterSha；
MR API 补拉时保存 diff_refs.base_sha / head_sha 到 review_tasks.before_sha / after_sha。
增加单文件 1 MiB、最多 20000 行限制，补 contract 测试。完成后停止。
```

### 输出

- GitLab raw file client。
- 任务详情 `diffContextCapabilities`。
- `GET /api/review-tasks/{taskId}/diff-context`。
- MR refs 持久化和后端 contract 测试。

### 授权边界

- 可以修改 `backend-python/`、README、API 契约、测试和本文档。
- 不实现前端展开按钮、暗黑高亮或 Patch 合并展示。
- 完成后必须停止，等待用户验证并确认“继续下一阶段”。

## 阶段 2：前端展开与暗黑高亮

### 阶段 Prompt

```text
在阶段 1 接口基础上实现共用 Diff 组件。默认紧凑展示；点击折叠占位区后按需拉取源码，
支持向上展开 20 行、向下展开 20 行和展开全部。查看 Diff 与 Patch 预览统一使用可切换的
明亮 / 暗黑主题，按文件后缀做 token 级语法高亮。完成前端 build 和浏览器验证后停止。
```

### 输出

- 共用可展开 Diff 组件。
- GitLab 风格分段展开交互。
- 普通 Diff 上下文展开；Patch 预览保留紧凑代码视图。
- 可切换明亮 / 暗黑主题的语法高亮。

### 授权边界

- 可以修改 `frontend/`、README、版本更新页和必要文档。
- 不新增数据库表，不修改 GitLab raw file 接口协议。
- 完成后必须停止，等待用户验证并确认“继续下一阶段”。

## 阶段 3：真实联调与收口

### 阶段 Prompt

```text
使用真实 GitLab MR 和 Push 任务联调上下文展开，覆盖修改、新增、删除和重命名文件。
补充 README 验证示例和新发现的避坑记录。完成后停止，等待验收。
```

### 授权边界

- 只做真实联调、必要修复和文档收口。
- 不扩展到在线编辑、应用 Patch 或提交 GitLab MR。
- 完成后必须停止，等待用户验收。

## 兼容策略

- 无 GitLab API 配置、无 refs、手动粘贴 diff、历史 MR 缺 base SHA：继续展示现有紧凑 diff，前端隐藏展开入口。
- Patch 预览保持紧凑展示，不再按 head `commitSha` 尝试拼接完整上下文。
- 旧 MR 普通 Diff 不临时使用当前 MR refs 冒充历史快照。
