# Review 反馈学习 V1 落地记录

## 状态

- 当前状态：已完成 V1 最小闭环
- 落地时间：2026-06-09
- 目标版本：V1 风险反馈记录闭环

## V1 目标

本阶段只打通“风险项 / AI finding -> 用户反馈 -> 反馈记录 -> 反馈池 -> 任务详情回显”的闭环。

V1 覆盖两类反馈对象：

1. 规则提醒卡片中的 `riskItems`。
2. 代码质量 AI Review 的 `findings`。

## V1 不做

- 不自动修改全局 Prompt。
- 不自动影响后续 Review 结果。
- 不做模型微调。
- 不把反馈自动沉淀为项目规则。
- 不做复杂 RAG / 知识库检索。
- 不调整任务列表的 AI finding 计数和 Review 状态语义。

## 最小数据结构

新增统一反馈表 `review_item_feedbacks`，用 `source_type` 区分反馈对象来源：

- `RULE_REMINDER`：规则提醒卡片项。
- `AI_FINDING`：代码质量 AI Review finding。

每条反馈通过 `task_id + source_type + item_fingerprint` 唯一定位，避免直接依赖前端数组下标。

## 最小接口

新增：

- `POST /api/review-tasks/{taskId}/feedback`
- `GET /api/review-tasks/{taskId}/feedback`
- `GET /api/risk-feedback`
- `PUT /api/risk-feedback/{feedbackId}/status`

增强：

- `GET /api/review-tasks/{taskId}/result`
- `GET /api/review-tasks/{taskId}/code-quality-results`
- `GET /api/review-tasks/{taskId}/code-quality-result`

增强后的提醒项 / AI finding 会携带 `feedbackKey` / `fingerprint` 和 `feedback`。

## 前端入口

新增和调整：

- 任务详情页：规则提醒项支持反馈。
- 任务详情页：AI finding 支持反馈。
- 顶部导航：新增“反馈池”。
- 反馈池页面：支持筛选、查看反馈、状态流转。

## 落地文件

后端：

- `backend-python/app/review_feedback/models.py`
- `backend-python/app/review_feedback/repository.py`
- `backend-python/app/review_feedback/service.py`
- `backend-python/app/review_feedback/api.py`
- `backend-python/app/main.py`
- `backend-python/app/review_record/repository.py`
- `backend-python/app/code_quality/repository.py`
- `backend-python/migrations/bootstrap_sql/V34__review_item_feedbacks.sql`
- `backend-python/tests/conftest.py`
- `backend-python/tests/contract/test_review_feedback_api_contract.py`

前端：

- `frontend/src/App.jsx`
- `frontend/src/styles.css`

文档：

- `docs/29-review-feedback-v1-implementation.md`

## 验证记录

已通过：

```powershell
.\scripts\run-backend.cmd test tests\contract\test_review_feedback_api_contract.py
```

结果：2 passed。

```powershell
.\scripts\run-frontend.cmd build
```

结果：build passed。

扩展验证：

```powershell
.\scripts\run-backend.cmd test tests\contract\test_review_tasks_api_contract.py tests\contract\test_code_quality_api_contract.py
```

结果：`test_review_tasks_api_contract.py` 通过；`test_code_quality_api_contract.py` 中 3 个既有契约点失败：

- `test_fix_preview_schema_removes_legacy_task_finding_unique_index`：当前 service 对不存在的 task 返回 404，而测试期望 200。
- `test_openai_and_anthropic_provider_mocks`：同一测试内项目默认 provider 从 OPENAI 改为 ANTHROPIC 后，第二次手动 Review 仍返回 OPENAI。
- `test_push_gate_debounces_recent_allowed_push`：首个 Push gate 决策返回 REJECTED，测试期望 ALLOWED。

这 3 个失败与 V1 feedback 新增 API、表结构和响应回显无直接耦合，本次未扩大修复范围。

## 后续 V2 方向

V2 再引入 `project_review_policies`，允许管理员把高质量反馈人工沉淀为项目规则候选，并在 Review 执行时以项目上下文形式注入。

详细方案见 `docs/30-review-feedback-v2-policy-plan.md`。
