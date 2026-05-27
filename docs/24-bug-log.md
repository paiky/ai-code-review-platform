# BUG 记录

本文从 2026-05-27 开始记录用户在真实使用中发现的 BUG、影响、根因和修复状态。每条记录都应包含可复现线索，便于后续回归验证。

## BUG-20260527-001 非默认项目组未配置钉钉机器人时误推送到默认项目组

状态：已修复

发现时间：2026-05-27

现象：

- 最新任务 `351` 属于 `IOS端` 项目组，项目为 `here/here-ios`，端类型为 `APP_IOS`。
- `IOS端` 项目组没有配置钉钉机器人。
- 任务仍推送到了 `默认通用项目组` 下配置的钉钉机器人。

期望：

- 默认项目组也是普通项目组，只服务归属默认项目组的项目。
- 非默认项目组没有启用钉钉机器人时，通知记录应为 `SKIPPED`。
- 不应回退发送到默认项目组或其它项目组机器人。

根因：

- `enabled_webhooks_for_task()` 在任务所属项目组没有启用机器人时，会主动回退查询默认项目组机器人。
- `_resolve_skipped_result()` 通过该回退逻辑判断存在可用机器人，因此允许继续发送。

修复：

- 任务通知只查询任务所属项目组的启用机器人。
- 任务所属项目组无机器人时直接返回 `DINGTALK_WEBHOOKS_EMPTY` / `SKIPPED`。
- 更新回归测试，确保空项目组不会调用默认项目组机器人。

回归验证：

- 运行 `backend-python/tests/contract/test_gitlab_dingtalk_integration.py::test_dingtalk_delivery_skips_when_project_group_has_no_webhooks`。
