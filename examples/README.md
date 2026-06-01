# Examples

## Push webhook quick check

`gitlab-push-webhook.mock.json` verifies that `Push Hook` can use the same URL as MR events:

```powershell
$payload = Get-Content -Raw -Path .\examples\gitlab-push-webhook.mock.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Push Hook" } `
  -Body $payload
```

本目录用于存放本地验证和联调用的示例数据。默认 Python 后端端口为 `8090`（见 `scripts/run-backend.cmd`）；若你改了端口，请同步替换下面示例 URL。

## 文件说明

- `gitlab-mr-webhook.mock.json`
  - 用于 P0 本地演示。
  - payload 自带 `changedFiles` 和 `diffText`。
  - 适合验证 `mock webhook -> analysis -> risk card -> 落库 -> 前端查看` 闭环。

- `gitlab-mr-webhook.real-no-changed-files.json`
  - 用于真实 GitLab 联调。
  - payload 不带 `changedFiles`，后端会按 `projectId + mrIid` 调 GitLab API 拉取 diff/change。
  - 使用前需要替换文件中的占位字段。

- `manual-review-request.json`
  - 用于验证手动审查接口 `POST /api/review-tasks/manual`。
  - 不依赖 GitLab webhook。

- `manual-review-value-config-request.json`
  - 用于验证 `@Value("${xxx}")` 配置感知。
  - 预期风险卡片中的 `focusIndicators` 会命中 `VALUE_CONFIG_CHANGE`。

- `gitlab.env.example`
  - 用于真实 GitLab 联调的本地环境变量模板。
  - 建议复制到 `.local/gitlab.env` 后再填写真实值。

如果个人电脑没有可用的 GitLab，可以使用仓库内的本地 GitLab CE Docker 配置，说明见 `local-gitlab/README.md`。

## 使用方式

### 1. Mock GitLab webhook

```powershell
$payload = Get-Content -Raw -Path .\examples\gitlab-mr-webhook.mock.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
  -Body $payload
```

### 2. 手动审查

```powershell
$payload = Get-Content -Raw -Path .\examples\manual-review-request.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/review-tasks/manual" `
  -ContentType "application/json" `
  -Body $payload
```

### 3. 真实 GitLab diff 联调

可以基于 `gitlab-mr-webhook.real-no-changed-files.json` 替换占位字段后执行：

```powershell
$payload = Get-Content -Raw -Path .\examples\gitlab-mr-webhook.real-no-changed-files.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
  -Body $payload
```

## 说明

- 本目录中的 JSON 为示例数据，不代表唯一合法请求。
- `.local/` 已加入 `.gitignore`，真实 token、MySQL 密码等敏感信息不要写回 `examples/`。
