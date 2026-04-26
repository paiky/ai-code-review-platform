# 本地开发避坑记录

## 1. Codex 沙箱内 Git 推送凭据问题

在当前 Windows + Codex 桌面环境里，普通沙箱命令执行 `git push origin main` 可能失败：

```text
error: cannot spawn sh: No such file or directory
error: failed to execute prompt script
fatal: could not read Username for 'https://github.com': No such file or directory
```

实际原因不是远端仓库或提交问题，而是 Git Credential Manager 需要调用 Git Bash 的 `sh.exe` 处理凭据提示；Codex 沙箱用户启动 `sh.exe` 时可能遇到 Windows 权限错误，例如：

```text
couldn't create signal pipe, Win32 error 5
```

处理方式：

1. 如果用户已授权沙箱外执行，可以用 escalated `git push`，让 Git Credential Manager 读取本机用户的 GitHub 凭据。
2. 如果仍失败，Codex 只完成 `git commit`，把 commit hash 和 `git push origin <branch>` 命令交给用户手动执行。

本次验证记录：

```text
普通沙箱 git push 失败。
沙箱外 git push origin main 成功。
成功推送提交：a24f593 Add local GitLab test environment
```
