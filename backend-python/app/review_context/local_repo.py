from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from threading import Lock
from time import perf_counter
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.core.config import Settings, get_settings


LOCAL_REPO_CONTEXT_TYPE = "LOCAL_REPOSITORY"
_MAX_REASON_CHARS = 500
_LOCKS: dict[str, Lock] = {}
_LOCKS_GUARD = Lock()


@dataclass
class _LocalRepoPlan:
    root: Path
    mirror_path: Path
    worktree_path: Path
    clone_url: str
    token: str
    timeout_seconds: int


class LocalRepoUnavailableError(Exception):
    pass


class LocalRepoGitError(Exception):
    def __init__(self, operation: str, return_code: int | None, output: str, token: str | None = None) -> None:
        self.operation = operation
        self.return_code = return_code
        self.output = _sanitize_text(output, token)
        super().__init__(self.public_message)

    @property
    def public_message(self) -> str:
        code = f"exitCode={self.return_code}" if self.return_code is not None else "timeout"
        output = _truncate(self.output.strip(), _MAX_REASON_CHARS)
        return f"git {self.operation} failed: {code}" + (f", error={output}" if output else "")


def prepare_local_repository_context(
    *,
    project_id: int | None,
    task_id: int | None,
    repository_url: str | None,
    git_project_id: str | None,
    head_ref: str | None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.local_repo_context_enabled:
        return _disabled_result(project_id, task_id)

    started = perf_counter()
    phase = "VALIDATE"
    try:
        plan = _build_plan(
            settings,
            project_id=project_id,
            task_id=task_id,
            repository_url=repository_url,
            git_project_id=git_project_id,
            head_ref=head_ref,
        )
        lock = _lock_for(str(plan.worktree_path))
        with lock:
            mirror_status = _prepare_mirror(plan)
            phase = "WORKTREE"
            _prepare_head_worktree(plan, str(head_ref))
        return _prepared_result(
            project_id=project_id,
            task_id=task_id,
            head_ref=head_ref,
            mirror_status=mirror_status,
            duration_ms=_duration_ms(started),
        )
    except LocalRepoUnavailableError as exception:
        return _unavailable_result(
            project_id=project_id,
            task_id=task_id,
            head_ref=head_ref,
            failure_phase=phase,
            reason=str(exception),
            duration_ms=_duration_ms(started),
        )
    except LocalRepoGitError as exception:
        return _unavailable_result(
            project_id=project_id,
            task_id=task_id,
            head_ref=head_ref,
            failure_phase=exception.operation.upper(),
            reason=exception.public_message,
            duration_ms=_duration_ms(started),
        )
    except Exception as exception:
        return _unavailable_result(
            project_id=project_id,
            task_id=task_id,
            head_ref=head_ref,
            failure_phase=phase,
            reason=_sanitize_text(str(exception), settings.gitlab_token),
            duration_ms=_duration_ms(started),
        )


def task_head_worktree_path(task_id: int | str | None) -> Path:
    settings = get_settings()
    if task_id is None:
        raise LocalRepoUnavailableError("Task id is unavailable; local repository worktree cannot be resolved.")
    root = _workspace_root(settings.local_repo_workspace_root)
    task_key = _safe_segment(str(task_id))
    return _child_path(root, "worktrees", task_key, "head")


def _build_plan(
    settings: Settings,
    *,
    project_id: int | None,
    task_id: int | None,
    repository_url: str | None,
    git_project_id: str | None,
    head_ref: str | None,
) -> _LocalRepoPlan:
    if project_id is None:
        raise LocalRepoUnavailableError("Project id is unavailable; local repository context is not prepared.")
    if task_id is None:
        raise LocalRepoUnavailableError("Task id is unavailable; local repository context is not prepared.")
    if not str(head_ref or "").strip():
        raise LocalRepoUnavailableError("Head commit/ref is unavailable; local repository context is not prepared.")

    root = _workspace_root(settings.local_repo_workspace_root)
    project_key = _safe_segment(str(project_id))
    task_key = _safe_segment(str(task_id))
    mirror_path = _child_path(root, "mirrors", f"{project_key}.git")
    worktree_path = _child_path(root, "worktrees", task_key, "head")
    clone_url = _clone_url(repository_url, git_project_id, settings)
    timeout_seconds = max(int(settings.local_repo_max_fetch_seconds or 0), 1)
    return _LocalRepoPlan(
        root=root,
        mirror_path=mirror_path,
        worktree_path=worktree_path,
        clone_url=clone_url,
        token=(settings.gitlab_token or "").strip(),
        timeout_seconds=timeout_seconds,
    )


def _prepare_mirror(plan: _LocalRepoPlan) -> str:
    plan.mirror_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.mirror_path.exists():
        _run_git(
            ["git", "--git-dir", str(plan.mirror_path), "fetch", "--prune"],
            token=plan.token,
            timeout_seconds=plan.timeout_seconds,
        )
        return "FETCHED"
    _run_git(
        ["git", "clone", "--mirror", plan.clone_url, str(plan.mirror_path)],
        token=plan.token,
        timeout_seconds=plan.timeout_seconds,
    )
    return "CLONED"


def _prepare_head_worktree(plan: _LocalRepoPlan, head_ref: str) -> None:
    _assert_within_root(plan.root, plan.worktree_path)
    plan.worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.worktree_path.exists():
        try:
            _run_git(
                ["git", "--git-dir", str(plan.mirror_path), "worktree", "remove", "--force", str(plan.worktree_path)],
                token=plan.token,
                timeout_seconds=plan.timeout_seconds,
            )
        except LocalRepoGitError:
            pass
        if plan.worktree_path.exists():
            _safe_rmtree(plan.root, plan.worktree_path)
    _run_git(
        [
            "git",
            "--git-dir",
            str(plan.mirror_path),
            "worktree",
            "add",
            "--detach",
            "--force",
            str(plan.worktree_path),
            head_ref,
        ],
        token=plan.token,
        timeout_seconds=plan.timeout_seconds,
    )


def _run_git(args: list[str], *, token: str | None, timeout_seconds: int) -> None:
    operation = _operation_name(args)
    env = _git_env(token, args)
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            env=env,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exception:
        raise LocalRepoGitError(operation, None, str(exception), token) from exception
    except OSError as exception:
        raise LocalRepoGitError(operation, None, str(exception), token) from exception
    if completed.returncode != 0:
        output = completed.stderr or completed.stdout or ""
        raise LocalRepoGitError(operation, completed.returncode, output, token)


def _git_env(token: str | None, args: list[str]) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    if token:
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        env["GIT_CONFIG_VALUE_0"] = f"PRIVATE-TOKEN: {token}"
    return env


def _operation_name(args: list[str]) -> str:
    for candidate in ("clone", "fetch", "worktree"):
        if candidate in args:
            return candidate
    return "command"


def _workspace_root(raw_root: str | None) -> Path:
    root = Path(raw_root or ".local/review-workspaces").expanduser().resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise LocalRepoUnavailableError("LOCAL_REPO_WORKSPACE_ROOT is not a directory.")
    return root


def _child_path(root: Path, *parts: str) -> Path:
    candidate = root.joinpath(*parts).resolve(strict=False)
    _assert_within_root(root, candidate)
    return candidate


def _assert_within_root(root: Path, candidate: Path) -> None:
    resolved_root = root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exception:
        raise LocalRepoUnavailableError("Resolved local repository path escapes LOCAL_REPO_WORKSPACE_ROOT.") from exception


def _safe_rmtree(root: Path, target: Path) -> None:
    _assert_within_root(root, target)
    if target.resolve(strict=False) == root.resolve(strict=False):
        raise LocalRepoUnavailableError("Refusing to remove LOCAL_REPO_WORKSPACE_ROOT.")
    shutil.rmtree(target)


def _clone_url(repository_url: str | None, git_project_id: str | None, settings: Settings) -> str:
    raw_url = str(repository_url or "").strip()
    if raw_url:
        return _normalize_clone_url(raw_url, settings.gitlab_token)
    git_project = str(git_project_id or "").strip().strip("/")
    base_url = str(settings.gitlab_base_url or "").strip().rstrip("/")
    if base_url and git_project and not git_project.isdigit():
        return _normalize_clone_url(f"{base_url}/{git_project}", settings.gitlab_token)
    raise LocalRepoUnavailableError(
        "Repository URL is unavailable; local repository mirror cannot be prepared from numeric GitLab project id alone."
    )


def _normalize_clone_url(raw_url: str, token: str | None) -> str:
    if raw_url.startswith(("http://", "https://")):
        parsed = urlparse(raw_url)
        if parsed.username or parsed.password:
            if not str(token or "").strip():
                raise LocalRepoUnavailableError(
                    "Repository URL contains credentials; configure GITLAB_TOKEN instead of using credentialed URLs."
                )
            parsed = parsed._replace(netloc=_netloc_without_credentials(parsed))
        path = parsed.path.split("/-/", 1)[0].rstrip("/")
        if path and not path.endswith(".git"):
            path = f"{path}.git"
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
    if raw_url.startswith("git@") or raw_url.startswith("ssh://"):
        return raw_url if raw_url.endswith(".git") else f"{raw_url}.git"
    raise LocalRepoUnavailableError("Repository URL must be an HTTP(S) or SSH Git URL.")


def _netloc_without_credentials(parsed) -> str:
    if not parsed.hostname:
        return ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.hostname}{port}"


def _safe_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    if normalized.strip(".-"):
        return normalized[:80]
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _lock_for(key: str) -> Lock:
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _LOCKS[key] = lock
        return lock


def _disabled_result(project_id: int | None, task_id: int | None) -> dict[str, Any]:
    summary = {
        "enabled": False,
        "status": "DISABLED",
    }
    return {"summary": summary, "unavailableContexts": []}


def _prepared_result(
    *,
    project_id: int | None,
    task_id: int | None,
    head_ref: str | None,
    mirror_status: str,
    duration_ms: int,
) -> dict[str, Any]:
    summary = {
        "enabled": True,
        "status": "PREPARED",
        "projectId": project_id,
        "taskId": task_id,
        "headRef": _short_ref(head_ref),
        "mirrorStatus": mirror_status,
        "worktreeStatus": "CHECKED_OUT",
        "durationMs": duration_ms,
        "sourceIncluded": False,
    }
    return {"summary": summary, "unavailableContexts": []}


def _unavailable_result(
    *,
    project_id: int | None,
    task_id: int | None,
    head_ref: str | None,
    failure_phase: str,
    reason: str,
    duration_ms: int,
) -> dict[str, Any]:
    public_reason = _truncate(_sanitize_text(reason, get_settings().gitlab_token), _MAX_REASON_CHARS)
    summary = {
        "enabled": True,
        "status": "UNAVAILABLE",
        "projectId": project_id,
        "taskId": task_id,
        "headRef": _short_ref(head_ref),
        "mirrorStatus": "UNAVAILABLE",
        "worktreeStatus": "SKIPPED",
        "failurePhase": failure_phase,
        "durationMs": duration_ms,
        "sourceIncluded": False,
    }
    return {
        "summary": summary,
        "unavailableContexts": [
            {
                "type": LOCAL_REPO_CONTEXT_TYPE,
                "reason": public_reason or "Local repository context is unavailable.",
            }
        ],
    }


def _short_ref(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"[0-9a-fA-F]{20,64}", text):
        return text[:12]
    return _truncate(text, 120)


def _duration_ms(started: float) -> int:
    return max(int((perf_counter() - started) * 1000), 0)


def _sanitize_text(value: str | None, token: str | None = None) -> str:
    text = str(value or "")
    if token:
        text = text.replace(token, "****")
    text = re.sub(r"(https?://)([^/\s@]+@)", r"\1****@", text)
    text = re.sub(r"(PRIVATE-TOKEN:\s*)\S+", r"\1****", text, flags=re.IGNORECASE)
    text = re.sub(r"(Authorization:\s*)\S+(?:\s+\S+)?", r"\1****", text, flags=re.IGNORECASE)
    return text


def _truncate(value: str | None, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."
