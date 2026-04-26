# Examples

本目录用于存放本地验证和联调用的示例数据。

## 文件说明

- `gitlab-mr-webhook.mock.json`
  - 用于 P0 本地演示。
  - payload 自带 `changedFiles` 和 `diffText`。
  - 适合验证 `mock webhook -> analysis -> risk card -> 落库 -> 前端查看` 闭环。

- `gitlab-mr-webhook.real-no-changed-files.json`
  - 用于真实 GitLab 联调。
  - payload 不带 `changedFiles`，后端会按 `projectId + mrIid` 调 GitLab API 拉取 diff/change。
  - 使用前需要替换文件中的占位字段，或者优先使用 `scripts/verify-gitlab-diff.cmd`。

- `manual-review-request.json`
  - 用于验证手动审查接口 `POST /api/review-tasks/manual`。
  - 不依赖 GitLab webhook。

- `gitlab.env.example`
  - 用于真实 GitLab 联调的本地环境变量模板。
  - 建议复制到 `.local/gitlab.env` 后再填写真实值。

## 使用方式

### 1. Mock GitLab webhook

```powershell
$payload = Get-Content -Raw -Path .\examples\gitlab-mr-webhook.mock.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
  -Body $payload
```

### 2. 手动审查

```powershell
$payload = Get-Content -Raw -Path .\examples\manual-review-request.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/review-tasks/manual" `
  -ContentType "application/json" `
  -Body $payload
```

### 3. 真实 GitLab diff 联调

建议优先走项目脚本：

```powershell
New-Item -ItemType Directory -Force .local
Copy-Item .\examples\gitlab.env.example .local\gitlab.env
.\scripts\run-backend.cmd
.\scripts\verify-gitlab-diff.cmd
```

如果手动发送 webhook，可以基于 `gitlab-mr-webhook.real-no-changed-files.json` 替换占位字段后执行：

```powershell
$payload = Get-Content -Raw -Path .\examples\gitlab-mr-webhook.real-no-changed-files.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
  -Body $payload
```

## 说明

- 本目录中的 JSON 为示例数据，不代表唯一合法请求。
- `.local/` 已加入 `.gitignore`，真实 token、MySQL 密码等敏感信息不要写回 `examples/`。
