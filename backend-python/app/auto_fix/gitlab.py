import base64
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import get_settings


class RemoteError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(message)


def full_sha(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{40}", value))


class GitLab:
    def __init__(self, project_id: str):
        settings = get_settings()
        self.project_id = project_id
        self.base_url = settings.gitlab_base_url.rstrip("/")
        self.token = settings.gitlab_token
        self.path = f"/api/v4/projects/{quote(project_id, safe='')}"
        self.trusted_url(self.base_url)

    def trusted_url(self, value: object) -> str:
        if not isinstance(value, str) or re.search(r"[\s<>\\\[\]()]", value):
            raise RemoteError("GITLAB_URL_INVALID", "GitLab 返回的地址无效")
        try:
            expected, actual = urlsplit(self.base_url), urlsplit(value)
            trusted = (
                expected.scheme == actual.scheme == "https"
                and expected.hostname
                and actual.hostname == expected.hostname
                and actual.port == expected.port
                and not actual.username and not actual.password
                and not actual.query and not actual.fragment
                and actual.path.startswith(expected.path.rstrip("/") + "/")
            )
            if value == self.base_url:
                trusted = (
                    actual.scheme == "https" and actual.hostname and not actual.username
                    and not actual.password and not actual.query and not actual.fragment
                )
        except ValueError:
            trusted = False
        if not trusted:
            raise RemoteError("GITLAB_URL_INVALID", "GitLab 地址需要使用已配置的 HTTPS 来源")
        return value

    def request(self, method: str, path: str = "", *, params=None, payload=None, missing_ok=False):
        if not self.token:
            raise RemoteError("PROJECT_NOT_AUTHORIZED", "平台未配置 GitLab 凭据")
        try:
            response = httpx.request(
                method, self.base_url + self.path + path, params=params, json=payload,
                headers={"PRIVATE-TOKEN": self.token}, timeout=15, follow_redirects=False,
            )
        except httpx.TransportError as error:
            raise RemoteError("GITLAB_UNAVAILABLE", "暂时无法确认 GitLab 请求结果", retryable=True) from error
        if response.status_code == 404 and missing_ok:
            return None
        if response.status_code in {408, 429} or response.status_code >= 500:
            raise RemoteError("GITLAB_UNAVAILABLE", "GitLab 服务暂时不可用", retryable=True)
        if not response.is_success:
            raise RemoteError("GITLAB_REQUEST_REJECTED", f"GitLab 拒绝操作（HTTP {response.status_code}）")
        try:
            return response.json()
        except ValueError as error:
            raise RemoteError("GITLAB_RESPONSE_INVALID", "GitLab 返回的数据无法读取", retryable=True) from error

    def project(self) -> dict:
        project = self.request("GET")
        if str(project.get("id")) != self.project_id:
            raise RemoteError("PROJECT_NOT_AUTHORIZED", "GitLab 返回的仓库与任务不一致")
        if project.get("merge_method") != "ff" or project.get("only_allow_merge_if_pipeline_succeeds") is not True:
            raise RemoteError("GITLAB_POLICY_CHANGED", "项目需启用仅快进合并及流水线通过要求")
        if project.get("squash_option") != "never":
            raise RemoteError("GITLAB_POLICY_CHANGED", "项目的 squash 设置不符合试点约束")
        if project.get("allow_merge_on_skipped_pipeline") is True:
            raise RemoteError("GITLAB_POLICY_CHANGED", "项目允许跳过流水线后合并")
        self.trusted_url(project.get("web_url"))
        self.trusted_url(project.get("http_url_to_repo"))
        return project

    def branch_sha(self, branch: str) -> str | None:
        row = self.request("GET", f"/repository/branches/{quote(branch, safe='')}", missing_ok=True)
        if row is None:
            return None
        sha = (row.get("commit") or {}).get("id")
        if not full_sha(sha):
            raise RemoteError("GITLAB_RESPONSE_INVALID", "GitLab 未返回有效的分支 SHA", retryable=True)
        return sha

    def merge_request(self, iid: str) -> dict:
        if not str(iid).isascii() or not str(iid).isdecimal():
            raise RemoteError("MR_INVALID", "原合并请求 IID 无效")
        return self.request("GET", f"/merge_requests/{iid}")

    def verify_original(self, iid: str, branch: str, sha: str) -> None:
        mr = self.merge_request(iid)
        if (
            str(mr.get("source_project_id")) != self.project_id
            or str(mr.get("target_project_id")) != self.project_id
            or mr.get("source_branch") != branch
        ):
            raise RemoteError("UNSUPPORTED_MR", "仅支持同仓库且源分支一致的 GitLab MR")
        if mr.get("state") != "opened":
            raise RemoteError("ORIGINAL_MR_CLOSED", "原 MR 已关闭或已合并")
        if (mr.get("diff_refs") or {}).get("head_sha") != sha or self.branch_sha(branch) != sha:
            raise RemoteError("BRANCH_CHANGED", "开发分支已更新，请查看新提交的 Review")

    def find_fix_mr(self, run_id: int, source: str, target: str) -> dict | None:
        rows = self.request("GET", "/merge_requests", params={
            "scope": "all", "source_branch": source, "target_branch": target, "per_page": 20,
        })
        matches = [
            row for row in rows
            if str(row.get("source_project_id")) == self.project_id
            and str(row.get("target_project_id")) == self.project_id
            and row.get("source_branch") == source and row.get("target_branch") == target
        ]
        if not matches:
            return None
        if len(matches) != 1 or f"<!-- auto-fix:{run_id} -->" not in (matches[0].get("description") or ""):
            raise RemoteError("FIX_MR_CONFLICT", "修复分支已有无法归属到本任务的 MR")
        return self.merge_request(str(matches[0]["iid"]))

    def create_fix_mr(self, run_id: int, source: str, target: str, description: str) -> dict:
        existing = self.find_fix_mr(run_id, source, target)
        if existing:
            return existing
        return self.request("POST", "/merge_requests", payload={
            "source_branch": source,
            "target_branch": target,
            "title": f"自动修复紧急风险（#{run_id}）",
            "description": f"<!-- auto-fix:{run_id} -->\n\n{description}",
            "squash": False,
            "remove_source_branch": False,
        })

    def fetch(self, repo: Path, git_url: str, *shas: str) -> None:
        if not all(full_sha(sha) for sha in shas):
            raise RemoteError("REVIEW_SNAPSHOT_INVALID", "审查提交 SHA 无效")
        _git(repo, "fetch", "--no-tags", "--no-recurse-submodules", self.trusted_url(git_url), *shas, token=self.token)

    def push(self, repo: Path, git_url: str, branch: str, sha: str, expected: str | None, base_sha: str) -> None:
        if not self.token or not full_sha(sha) or not full_sha(base_sha):
            raise RemoteError("PROJECT_NOT_AUTHORIZED", "修复提交缺少有效的写入授权")
        ref = f"refs/heads/{branch}"
        _git(repo, "check-ref-format", ref)
        _git(repo, "merge-base", "--is-ancestor", expected or base_sha, sha)
        _git(
            repo, "push", "--no-verify", f"--force-with-lease={ref}:{expected or ''}",
            self.trusted_url(git_url), f"{sha}:{ref}", token=self.token,
        )


def prepare_repo(root: Path, run_id: int) -> Path:
    repo = root / f"fix-{run_id}.git"
    root.mkdir(parents=True, exist_ok=True)
    if repo.is_symlink() or repo.resolve() != repo:
        raise RemoteError("WORKSPACE_INVALID", "修复工作区路径无效")
    repo.mkdir(exist_ok=True)
    if not (repo / "config").exists():
        _git(repo, "init", "--bare", "--template=", ".")
    return repo


def _git(repo: Path, *args: str, token: str | None = None) -> None:
    env = {key: val for key, val in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    if token:
        auth = base64.b64encode(f"oauth2:{token}".encode()).decode("ascii")
        env.update(
            GIT_CONFIG_COUNT="2",
            GIT_CONFIG_KEY_0="http.extraHeader", GIT_CONFIG_VALUE_0=f"Authorization: Basic {auth}",
            GIT_CONFIG_KEY_1="http.followRedirects", GIT_CONFIG_VALUE_1="false",
        )
    try:
        process = subprocess.run(
            ["git", *args], cwd=repo, env=env, capture_output=True, timeout=90, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RemoteError("GIT_OPERATION_UNAVAILABLE", "Git 操作暂不可用", retryable=bool(token)) from error
    if process.returncode != 0:
        raise RemoteError("GIT_OPERATION_FAILED", "Git 操作无法完成", retryable=bool(token))
