# Local GitLab

本目录用于在个人电脑上启动一个本地 GitLab CE，模拟真实 MR、GitLab API 和 MR webhook。

用途：

- 创建测试项目、分支和 Merge Request。
- 给后端配置 `GITLAB_BASE_URL=http://localhost:8929`。
- 验证 payload 不带 `changedFiles` 时，后端通过 GitLab API 拉取真实 diff/change。
- 配置 GitLab MR webhook，回调本地后端。

## 前提

- Docker Desktop 已安装并启动。
- 当前 Windows 用户需要能访问 Docker daemon。通常需要在 `docker-users` 组里。
- 建议预留至少 4GB 内存给 Docker Desktop。GitLab 首次启动可能需要 5 到 10 分钟。

说明：GitLab 官方生产文档不推荐 Docker for Windows 作为生产部署方式，但本项目只用于本地模拟和联调。

## 启动

从仓库根目录执行：

```powershell
New-Item -ItemType Directory -Force .local | Out-Null
if (-not (Test-Path .local\local-gitlab.env)) {
    Copy-Item local-gitlab\.env.example .local\local-gitlab.env
}
docker compose --env-file .local/local-gitlab.env -f local-gitlab/docker-compose.yml up -d
```

启动后访问：

```text
http://localhost:8929
```

默认账号：

```text
username: root
password: Acr!9vKp47mQzLs2026
```

首次启动前可在 `.local/local-gitlab.env` 修改初始密码或镜像版本。Compose 的容器 HTTP 端口固定为 `8929`，需要改端口时同时核对 GitLab `external_url`、端口映射与后端 GitLab 地址。已有数据目录中的账号密码以 GitLab 内的实际设置为准。

说明：GitLab 会拒绝包含常见词组合的弱密码。如果你自定义 `LOCAL_GITLAB_ROOT_PASSWORD`，请使用足够随机的强密码。

默认镜像固定为：

```text
gitlab/gitlab-ce:14.10.5-ce.0
```

原因：本项目需要模拟 MR webhook 和 MR diff/change API，GitLab 14.x 足够，并且更贴近公司 GitLab 14.5。`latest` 版本初始化更重，在 Docker Desktop + Windows bind mount 下更容易因为 PostgreSQL 初始化超时而失败。

## 查看启动日志

```powershell
docker compose --env-file .local/local-gitlab.env -f local-gitlab/docker-compose.yml logs --tail=100 gitlab
```

看到 GitLab 页面可访问后再继续创建项目。首次初始化比较慢。

## 后端联调配置

1. 在 GitLab UI 创建测试项目。
2. 在项目里创建一个默认分支，例如 `main`。
3. 新建一个 feature 分支，修改文件并创建 Merge Request。
4. 在 root 用户的 Access Tokens 页面创建一个带 `api` scope 的 token。
5. 复制示例环境变量：

```powershell
if (-not (Test-Path .local\gitlab.env)) {
    Copy-Item examples\gitlab.env.example .local\gitlab.env
}
```

6. 修改 `.local/gitlab.env`：

```text
GITLAB_BASE_URL=http://localhost:8929
GITLAB_TOKEN=<root 或项目 token>
GITLAB_PROJECT_ID=<项目 id>
GITLAB_MR_IID=<MR iid，不是数据库 id>
GITLAB_API_ENABLED=true
```

7. 按根 README 准备数据库，再启动或重启后端：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-backend.ps1 dev
```

在另一终端调用 `Invoke-RestMethod http://localhost:8090/api/health` 确认后端就绪。配置下面的回调后，发起真实 MR，在任务详情核对 changed files 和 diff。也可使用 [真实 GitLab diff 联调示例](../examples/README.md#4-真实-gitlab-diff-联调)。

## 配置真实 webhook 回调本地后端

在 GitLab 项目页面进入：

```text
Settings -> Webhooks
```

Webhook URL 填：

```text
http://host.docker.internal:8090/api/webhooks/gitlab/merge-request
```

选择 `Merge request events` 后保存并测试。

注意：

- 如果后端使用非默认端口，需要同步修改 URL。
- 本地 GitLab 配置已设置允许 webhook 请求本地网络。
- 如果仍提示 local network 被阻止，到 Admin Area 的 outbound request 设置里确认允许本地网络请求。

## 停止

```powershell
docker compose --env-file .local/local-gitlab.env -f local-gitlab/docker-compose.yml stop gitlab
```

停止不会删除 `.local/gitlab` 下的数据。需要重置 GitLab 时，先停止容器，再手动删除 `.local/gitlab`。
