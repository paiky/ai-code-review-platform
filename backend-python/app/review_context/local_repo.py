from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from threading import Lock
from time import perf_counter, time
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.core.config import Settings, get_settings


LOCAL_REPO_CONTEXT_TYPE = "LOCAL_REPOSITORY"
_MAX_REASON_CHARS = 500
_MAX_CLEANUP_ERROR_CHARS = 240
_MAX_CLEANUP_ERRORS = 3
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
        return _disabled_result(project_id, task_id, settings)

    started = perf_counter()
    phase = "VALIDATE"
    cleanup_summary: dict[str, Any] | None = None
    plan: _LocalRepoPlan | None = None
    try:
        plan = _build_plan(
            settings,
            project_id=project_id,
            task_id=task_id,
            repository_url=repository_url,
            git_project_id=git_project_id,
            head_ref=head_ref,
        )
        cleanup_summary = _cleanup_workspace_best_effort(
            settings,
            current_task_id=task_id,
            current_project_id=project_id,
        )
        mirror_lock = _lock_for(str(plan.mirror_path))
        worktree_lock = _lock_for(str(plan.worktree_path))
        with mirror_lock:
            with worktree_lock:
                mirror_status = _prepare_mirror(plan)
                phase = "WORKTREE"
                _prepare_head_worktree(plan, str(head_ref))
        return _prepared_result(
            project_id=project_id,
            task_id=task_id,
            head_ref=head_ref,
            plan=plan,
            settings=settings,
            mirror_status=mirror_status,
            duration_ms=_duration_ms(started),
            cleanup_summary=cleanup_summary,
        )
    except LocalRepoUnavailableError as exception:
        return _unavailable_result(
            project_id=project_id,
            task_id=task_id,
            head_ref=head_ref,
            plan=plan,
            settings=settings,
            failure_phase=phase,
            reason=str(exception),
            duration_ms=_duration_ms(started),
            cleanup_summary=cleanup_summary,
        )
    except LocalRepoGitError as exception:
        return _unavailable_result(
            project_id=project_id,
            task_id=task_id,
            head_ref=head_ref,
            plan=plan,
            settings=settings,
            failure_phase=exception.operation.upper(),
            reason=exception.public_message,
            duration_ms=_duration_ms(started),
            cleanup_summary=cleanup_summary,
        )
    except Exception as exception:
        return _unavailable_result(
            project_id=project_id,
            task_id=task_id,
            head_ref=head_ref,
            plan=plan,
            settings=settings,
            failure_phase=phase,
            reason=_sanitize_text(str(exception), settings.gitlab_token),
            duration_ms=_duration_ms(started),
            cleanup_summary=cleanup_summary,
        )


def task_head_worktree_path(task_id: int | str | None) -> Path:
    settings = get_settings()
    if task_id is None:
        raise LocalRepoUnavailableError("Task id is unavailable; local repository worktree cannot be resolved.")
    root = _workspace_root(settings.local_repo_workspace_root)
    task_key = _safe_segment(str(task_id))
    return _child_path(root, "worktrees", task_key, "head")


def cleanup_local_repository_workspace(
    *,
    current_task_id: int | str | None = None,
    current_project_id: int | str | None = None,
) -> dict[str, Any]:
    return _cleanup_workspace_best_effort(
        get_settings(),
        current_task_id=current_task_id,
        current_project_id=current_project_id,
    )


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
        _touch_path(plan.mirror_path)
        return "FETCHED"
    _run_git(
        ["git", "clone", "--mirror", plan.clone_url, str(plan.mirror_path)],
        token=plan.token,
        timeout_seconds=plan.timeout_seconds,
    )
    _touch_path(plan.mirror_path)
    return "CLONED"


def _prepare_head_worktree(plan: _LocalRepoPlan, head_ref: str) -> None:
    _assert_within_root(plan.root, plan.worktree_path)
    plan.worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.worktree_path.exists():
        try:
            _run_git(
                [
                    "git",
                    "--git-dir",
                    str(plan.mirror_path),
                    "worktree",
                    "remove",
                    "--force",
                    str(plan.worktree_path),
                ],
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
    _touch_path(plan.worktree_path.parent)


def _cleanup_workspace_best_effort(
    settings: Settings,
    *,
    current_task_id: int | str | None,
    current_project_id: int | str | None,
) -> dict[str, Any]:
    started = perf_counter()
    summary = _cleanup_summary_base(settings)
    if not settings.local_repo_cleanup_enabled:
        summary["durationMs"] = _duration_ms(started)
        return summary
    try:
        root = _workspace_root(settings.local_repo_workspace_root)
        summary["enabled"] = True
        summary["status"] = "COMPLETED"
        if summary["worktreeRetentionHours"] > 0:
            _cleanup_stale_worktrees(
                root,
                retention_hours=summary["worktreeRetentionHours"],
                current_task_id=current_task_id,
                summary=summary,
                token=settings.gitlab_token,
            )
        if summary["mirrorRetentionDays"] > 0:
            _cleanup_stale_mirrors(
                root,
                retention_days=summary["mirrorRetentionDays"],
                current_project_id=current_project_id,
                summary=summary,
                token=settings.gitlab_token,
            )
    except Exception as exception:
        summary["enabled"] = True
        _record_cleanup_error(
            summary,
            _cleanup_error("workspace", exception),
            settings.gitlab_token,
        )
    summary["durationMs"] = _duration_ms(started)
    if summary["errorCount"] > 0 and summary["status"] == "COMPLETED":
        summary["status"] = "PARTIAL"
    return summary


def _cleanup_summary_base(settings: Settings) -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "DISABLED",
        "worktreeRetentionHours": max(int(settings.local_repo_worktree_retention_hours or 0), 0),
        "mirrorRetentionDays": max(int(settings.local_repo_mirror_retention_days or 0), 0),
        "scannedWorktreeCount": 0,
        "deletedWorktreeCount": 0,
        "skippedWorktreeCount": 0,
        "scannedMirrorCount": 0,
        "deletedMirrorCount": 0,
        "skippedMirrorCount": 0,
        "bytesDeleted": 0,
        "errorCount": 0,
        "errors": [],
        "durationMs": 0,
    }


def _cleanup_stale_worktrees(
    root: Path,
    *,
    retention_hours: int,
    current_task_id: int | str | None,
    summary: dict[str, Any],
    token: str | None,
) -> None:
    worktrees_root = _child_path(root, "worktrees")
    if not worktrees_root.exists():
        return
    current_task_key = _safe_segment(str(current_task_id)) if current_task_id is not None else None
    cutoff = time() - (retention_hours * 60 * 60)
    for candidate in _iter_directories(worktrees_root):
        summary["scannedWorktreeCount"] += 1
        if current_task_key and candidate.name == current_task_key:
            summary["skippedWorktreeCount"] += 1
            continue
        try:
            _assert_deletable_workspace_child(root, candidate)
            if _last_modified_at(candidate) > cutoff:
                summary["skippedWorktreeCount"] += 1
                continue
            lock = _lock_for(str(candidate.joinpath("head").resolve(strict=False)))
            if not lock.acquire(blocking=False):
                summary["skippedWorktreeCount"] += 1
                continue
            try:
                size = _directory_size(candidate)
                _safe_rmtree(root, candidate)
                summary["deletedWorktreeCount"] += 1
                summary["bytesDeleted"] += size
            finally:
                lock.release()
        except Exception as exception:
            _record_cleanup_error(summary, _cleanup_error("worktree", exception), token)


def _cleanup_stale_mirrors(
    root: Path,
    *,
    retention_days: int,
    current_project_id: int | str | None,
    summary: dict[str, Any],
    token: str | None,
) -> None:
    mirrors_root = _child_path(root, "mirrors")
    if not mirrors_root.exists():
        return
    current_project_key = (
        _safe_segment(str(current_project_id)) if current_project_id is not None else None
    )
    current_mirror_name = f"{current_project_key}.git" if current_project_key else None
    cutoff = time() - (retention_days * 24 * 60 * 60)
    for candidate in _iter_directories(mirrors_root):
        if not candidate.name.endswith(".git"):
            continue
        summary["scannedMirrorCount"] += 1
        if current_mirror_name and candidate.name == current_mirror_name:
            summary["skippedMirrorCount"] += 1
            continue
        try:
            _assert_deletable_workspace_child(root, candidate)
            if _last_modified_at(candidate) > cutoff:
                summary["skippedMirrorCount"] += 1
                continue
            lock = _lock_for(str(candidate.resolve(strict=False)))
            if not lock.acquire(blocking=False):
                summary["skippedMirrorCount"] += 1
                continue
            try:
                size = _directory_size(candidate)
                _safe_rmtree(root, candidate)
                summary["deletedMirrorCount"] += 1
                summary["bytesDeleted"] += size
            finally:
                lock.release()
        except Exception as exception:
            _record_cleanup_error(summary, _cleanup_error("mirror", exception), token)


def _iter_directories(parent: Path) -> list[Path]:
    try:
        return [item for item in parent.iterdir() if item.is_dir()]
    except OSError:
        return []


def _assert_deletable_workspace_child(root: Path, target: Path) -> None:
    _assert_within_root(root, target)
    resolved_root = root.resolve(strict=False)
    resolved_target = target.resolve(strict=False)
    protected = {
        resolved_root,
        _child_path(root, "worktrees").resolve(strict=False),
        _child_path(root, "mirrors").resolve(strict=False),
    }
    if resolved_target in protected:
        raise LocalRepoUnavailableError(
            "Refusing to remove protected local repository workspace path."
        )


def _last_modified_at(target: Path) -> float:
    return target.stat().st_mtime


def _directory_size(target: Path) -> int:
    total = 0
    for root_dir, dir_names, file_names in os.walk(target, followlinks=False):
        root_path = Path(root_dir)
        for dir_name in dir_names:
            directory = root_path / dir_name
            if directory.is_symlink():
                try:
                    total += directory.lstat().st_size
                except OSError:
                    continue
        for file_name in file_names:
            file_path = root_path / file_name
            try:
                total += file_path.lstat().st_size
            except OSError:
                continue
    return total


def _record_cleanup_error(summary: dict[str, Any], message: str, token: str | None) -> None:
    summary["status"] = "PARTIAL"
    summary["errorCount"] += 1
    if len(summary["errors"]) >= _MAX_CLEANUP_ERRORS:
        return
    summary["errors"].append(_truncate(_sanitize_text(message, token), _MAX_CLEANUP_ERROR_CHARS))


def _cleanup_error(scope: str, exception: Exception) -> str:
    return f"{scope} cleanup failed: {exception.__class__.__name__}"


def _touch_path(path: Path) -> None:
    try:
        os.utime(path, None)
    except OSError:
        pass


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
        env["GIT_CONFIG_VALUE_0"] = _git_basic_auth_header(token)
    return env


def _git_basic_auth_header(token: str) -> str:
    encoded = _git_basic_auth_value(token)
    return f"Authorization: Basic {encoded}"


def _git_basic_auth_value(token: str) -> str:
    credential = f"oauth2:{token}".encode("utf-8")
    return base64.b64encode(credential).decode("ascii")


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


def _disabled_result(project_id: int | None, task_id: int | None, settings: Settings) -> dict[str, Any]:
    summary = {
        "enabled": False,
        "status": "DISABLED",
        "sourceWorkspaceSummary": _source_workspace_summary(
            settings=settings,
            plan=None,
            enabled=False,
            status="DISABLED",
            mirror_status="SKIPPED",
            worktree_status="SKIPPED",
            failure_phase="LOCAL_REPO_CONTEXT_DISABLED",
            cleanup_summary=None,
        ),
    }
    return {"summary": summary, "unavailableContexts": []}


def _prepared_result(
    *,
    project_id: int | None,
    task_id: int | None,
    head_ref: str | None,
    plan: _LocalRepoPlan,
    settings: Settings,
    mirror_status: str,
    duration_ms: int,
    cleanup_summary: dict[str, Any] | None,
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
    _attach_cleanup_summary(summary, cleanup_summary)
    _attach_source_workspace_summary(
        summary,
        _source_workspace_summary(
            settings=settings,
            plan=plan,
            enabled=True,
            status="PREPARED",
            mirror_status=mirror_status,
            worktree_status="CHECKED_OUT",
            cleanup_summary=cleanup_summary,
        ),
    )
    return {"summary": summary, "unavailableContexts": []}


def _unavailable_result(
    *,
    project_id: int | None,
    task_id: int | None,
    head_ref: str | None,
    plan: _LocalRepoPlan | None,
    settings: Settings,
    failure_phase: str,
    reason: str,
    duration_ms: int,
    cleanup_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    public_reason = _truncate(
        _sanitize_text(reason, get_settings().gitlab_token),
        _MAX_REASON_CHARS,
    )
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
    _attach_cleanup_summary(summary, cleanup_summary)
    _attach_source_workspace_summary(
        summary,
        _source_workspace_summary(
            settings=settings,
            plan=plan,
            enabled=True,
            status="UNAVAILABLE",
            mirror_status=_mirror_status_for_failure(plan, failure_phase),
            worktree_status=_worktree_status_for_failure(failure_phase),
            failure_phase=failure_phase,
            cleanup_summary=cleanup_summary,
        ),
    )
    return {
        "summary": summary,
        "unavailableContexts": [
            {
                "type": LOCAL_REPO_CONTEXT_TYPE,
                "reason": public_reason or "Local repository context is unavailable.",
            }
        ],
    }


def _attach_cleanup_summary(
    summary: dict[str, Any],
    cleanup_summary: dict[str, Any] | None,
) -> None:
    if cleanup_summary is not None:
        summary["cleanup"] = cleanup_summary


def _attach_source_workspace_summary(
    summary: dict[str, Any],
    source_workspace_summary: dict[str, Any],
) -> None:
    summary["sourceWorkspaceSummary"] = source_workspace_summary


def _source_workspace_summary(
    *,
    settings: Settings,
    plan: _LocalRepoPlan | None,
    enabled: bool,
    status: str,
    mirror_status: str,
    worktree_status: str,
    cleanup_summary: dict[str, Any] | None,
    failure_phase: str | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "enabled": bool(enabled),
        "status": status,
        "mode": "GIT_MIRROR_AND_TASK_WORKTREE",
        "cleanupPolicy": {
            "enabled": bool(settings.local_repo_cleanup_enabled),
            "worktreeRetentionHours": max(int(settings.local_repo_worktree_retention_hours or 0), 0),
            "mirrorRetentionDays": max(int(settings.local_repo_mirror_retention_days or 0), 0),
        },
    }
    if cleanup_summary is not None:
        summary["cleanup"] = cleanup_summary
    if failure_phase:
        summary["failurePhase"] = failure_phase
    if plan is None:
        summary["mirror"] = {"exists": False, "status": mirror_status}
        summary["worktree"] = {"exists": False, "status": worktree_status}
        return summary

    summary["remoteUrl"] = _public_remote_url(plan.clone_url, plan.token)
    summary["mirror"] = _workspace_path_summary(
        plan.mirror_path,
        status=mirror_status,
        timestamp_label="lastFetchedAt",
    )
    summary["worktree"] = _workspace_path_summary(
        plan.worktree_path,
        status=worktree_status,
        timestamp_label="lastCheckedOutAt",
    )
    return summary


def _workspace_path_summary(
    path: Path,
    *,
    status: str,
    timestamp_label: str,
) -> dict[str, Any]:
    exists = path.exists()
    result: dict[str, Any] = {
        "exists": bool(exists),
        "status": status,
    }
    touched_at = _path_modified_at(path)
    if touched_at:
        result[timestamp_label] = touched_at
    return result


def _path_modified_at(path: Path) -> str | None:
    try:
        modified_at = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(modified_at, tz=timezone.utc).isoformat(timespec="seconds")


def _public_remote_url(value: str, token: str | None) -> str:
    return _truncate(_sanitize_text(value, token), 240)


def _mirror_status_for_failure(plan: _LocalRepoPlan | None, failure_phase: str) -> str:
    if plan is None:
        return "SKIPPED"
    if str(failure_phase or "").upper() in {"CLONE", "FETCH"}:
        return "UNAVAILABLE"
    return "PRESENT" if plan.mirror_path.exists() else "MISSING"


def _worktree_status_for_failure(failure_phase: str) -> str:
    phase = str(failure_phase or "").upper()
    if phase == "WORKTREE":
        return "CHECKOUT_FAILED"
    return "SKIPPED"


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
        text = text.replace(_git_basic_auth_value(token), "****")
    text = re.sub(r"(https?://)([^/\s@]+@)", r"\1****@", text)
    text = re.sub(r"(PRIVATE-TOKEN:\s*)\S+", r"\1****", text, flags=re.IGNORECASE)
    text = re.sub(r"(Authorization:\s*)\S+(?:\s+\S+)?", r"\1****", text, flags=re.IGNORECASE)
    return text


def _truncate(value: str | None, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."
