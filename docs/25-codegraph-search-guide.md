# CodeGraph 与 rg 搜索指南

## 状态

当前有效。用于本仓库日常开发、排查和 Agent 协作。

## 目标

本仓库同时使用 CodeGraph MCP 和 `rg`。两者不是替代关系：

- `rg` 适合快速定位代码中真实存在的字符串。
- CodeGraph 适合从业务问题建立 Python 后端候选地图，并在拿到关键符号后展开调用关系。

默认工作流：

```text
已知字符串、路径、日志或配置
  -> rg 定位
  -> 阅读局部源码

已知关键符号，且需要跨模块调用链或影响分析
  -> codegraph_callers / codegraph_callees / codegraph_trace / codegraph_impact
  -> 阅读局部源码

CodeGraph 不可用或查询失败
  -> 直接使用 rg
  -> 不做安装、配置或索引排障，除非当前任务明确要求
```

## 使用规则

### 优先使用 CodeGraph 的场景

- 已知关键函数，需要确认调用者、被调用函数、影响范围或跨模块链路。
- `rg` 与局部源码阅读不足以确定 Python 后端调用关系。

单个任务默认最多调用两次 CodeGraph。获得候选链路后转为阅读局部源码，不重复执行同类查询。

常用 MCP 工具：

```text
codegraph_context
codegraph_search
codegraph_callers
codegraph_callees
codegraph_trace
codegraph_impact
```

### 优先使用 rg 的场景

- 已知接口路径、字段名、数据库列、配置项、错误文案或日志内容。
- 搜索 React 前端页面、组件、请求路径和展示文案。
- 排查文档、脚本、环境或工具链问题，以及完成简单局部修改、测试修复或样式调整。
- 核对 CodeGraph 返回的调用位置是否真实存在。
- CodeGraph 未识别动态调用、异步调度或框架边界。

仓库根目录提供 `.rgignore`。使用 `rg` 时不要扫描依赖、构建产物和停止维护的 Java 后端。

### 必须交叉核验的场景

- CodeGraph 的模糊查询结果与业务问题不一致。
- `codegraph_callers` 返回空结果，但源码可能存在调用。
- `codegraph_trace` 提示无法跨越动态分派、回调、异步任务或框架 hook。
- 改动涉及通知、调度队列、数据库兼容或跨模块主链路。

## 实测记录

测试日期：2026-06-02。

测试环境中的 CodeGraph 索引包含 63 个文件、1374 个节点、3882 条边。Python 后端覆盖较好；前端已进入索引，但模糊语义查询质量不稳定。

| 场景 | rg | CodeGraph | 建议 |
| --- | ---: | ---: | --- |
| 主链路关键词定位 | 约 63 ms | 首次 `codegraph_context` 约 13.7 s | 先用 `rg` 快速落点 |
| 三组聚焦字符串搜索 | 约 169 ms | 精确 `codegraph_search` 约 1.8 s | 已知字符串时用 `rg` |
| 反查 `_process_task` 调用者 | 需要阅读命中结果 | `codegraph_callers` 一次返回 MR、Push、rerun 三个入口 | 已知函数后用 CodeGraph |
| 展开 `trigger_auto_review -> _run_review` | 需要多次搜索和阅读 | `codegraph_trace` 约 7.1 s，直接返回函数体和 Provider 调用 | 后端链路追踪用 CodeGraph |
| 前端任务详情请求定位 | `rg` 直接命中 `App.jsx` | 模糊查询错误返回后端模型 | 前端优先用 `rg` |

## 已知边界

CodeGraph 是静态图，不是唯一事实来源。

本次实测中：

- `codegraph_callers("trigger_auto_review")` 没有识别到实际调用者，但 `rg` 能在 `backend-python/app/project_integration/service.py` 中直接找到 `_process_task -> trigger_auto_review`。
- `codegraph_trace("_process_task", "create_scheduler_job")` 无法完整跨越异步调度边界。
- 前端语义查询“任务详情页如何请求并展示 code quality review 结果和进度”错误返回了后端模型。

因此，CodeGraph 返回结果必须结合局部源码或 `rg` 命中核验。

## 典型示例

### 排查 Push 为什么没有触发 AI Review

```text
1. codegraph_context：描述 Push 未触发 AI Review 的业务现象
2. rg：搜索 trigger_auto_review、pushBranchPatterns、GLOBAL_DISABLED、reason_code
3. codegraph_callees(trigger_auto_review)：展开 Push gate、调度和通知分支
4. 阅读 backend-python/app/code_quality/service.py 的局部源码确认实际条件
```

### 定位前端任务详情页的进度请求

```text
1. rg：搜索 code-quality-progress、code-quality-result、code-quality-results
2. 阅读 frontend/src/App.jsx 的局部源码
3. 如需继续追后端，再对命中的 Python service 函数使用 CodeGraph
```

## 索引维护

首次启用或索引不可用时：

```powershell
.\scripts\setup-codegraph.ps1
```

修改忽略规则后需要强制重建索引：

```powershell
codegraph.cmd index --force
```

日常增量同步：

```powershell
codegraph.cmd sync
```

Codex App 与 Cursor 的 MCP 配置和常见问题见 `docs/11-agent-environment-pitfalls.md`。
