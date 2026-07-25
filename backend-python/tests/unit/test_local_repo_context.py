from __future__ import annotations

import base64
import os
from pathlib import Path
import time

import pytest

from app.review_context import local_repo
from app.review_context.local_repo import (
    cleanup_local_repository_workspace,
    prepare_local_repository_context,
)


def test_local_repo_context_is_disabled_by_default() -> None:
    context = prepare_local_repository_context(
        project_id=1,
        task_id=101,
        repository_url="https://gitlab.example.com/demo/service",
        git_project_id="1001",
        head_ref="head-sha",
    )

    assert context["summary"]["status"] == "DISABLED"
    assert context["summary"]["enabled"] is False
    assert context["unavailableContexts"] == []


def test_local_repo_context_clones_mirror_and_checks_out_head_worktree(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def fake_run_git(args: list[str], *, token: str | None, timeout_seconds: int) -> None:
        commands.append(args)
        assert token == "unit-token"
        assert timeout_seconds == 7

    monkeypatch.setenv("LOCAL_REPO_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("LOCAL_REPO_MAX_FETCH_SECONDS", "7")
    monkeypatch.setenv("GITLAB_TOKEN", "unit-token")
    monkeypatch.setattr(local_repo, "_run_git", fake_run_git)

    context = prepare_local_repository_context(
        project_id=1,
        task_id=101,
        repository_url="https://gitlab.example.com/demo/service",
        git_project_id="1001",
        head_ref="2222222222222222222222222222222222222222",
    )

    summary = context["summary"]
    assert summary["status"] == "PREPARED"
    assert summary["mirrorStatus"] == "CLONED"
    assert summary["worktreeStatus"] == "CHECKED_OUT"
    assert summary["headRef"] == "222222222222"
    assert summary["sourceIncluded"] is False
    workspace = summary["sourceWorkspaceSummary"]
    assert workspace["enabled"] is True
    assert workspace["status"] == "PREPARED"
    assert workspace["mode"] == "GIT_MIRROR_AND_TASK_WORKTREE"
    assert workspace["remoteUrl"] == "https://gitlab.example.com/demo/service.git"
    assert workspace["mirror"]["status"] == "CLONED"
    assert workspace["worktree"]["status"] == "CHECKED_OUT"
    assert workspace["cleanupPolicy"]["worktreeRetentionHours"] == 24
    assert workspace["cleanupPolicy"]["mirrorRetentionDays"] == 30
    assert context["unavailableContexts"] == []
    assert commands[0][:3] == ["git", "clone", "--mirror"]
    assert commands[0][3] == "https://gitlab.example.com/demo/service.git"
    assert commands[1][0:4] == ["git", "--git-dir", str(tmp_path / "workspaces" / "mirrors" / "1.git"), "worktree"]
    assert "unit-token" not in str(commands)


def test_local_repo_git_env_uses_basic_auth_header_without_credentialed_url() -> None:
    env = local_repo._git_env("unit-token", ["git", "clone", "--mirror"])
    encoded = base64.b64encode(b"oauth2:unit-token").decode("ascii")

    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert env["GIT_CONFIG_VALUE_0"] == f"Authorization: Basic {encoded}"
    assert "unit-token" not in env["GIT_CONFIG_VALUE_0"]
    assert "PRIVATE-TOKEN" not in env["GIT_CONFIG_VALUE_0"]


def test_local_repo_context_fetches_existing_mirror(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    (root / "mirrors" / "1.git").mkdir(parents=True)
    commands: list[list[str]] = []

    monkeypatch.setenv("LOCAL_REPO_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setattr(local_repo, "_run_git", lambda args, **_kwargs: commands.append(args))

    context = prepare_local_repository_context(
        project_id=1,
        task_id=102,
        repository_url="https://gitlab.example.com/demo/service.git",
        git_project_id="1001",
        head_ref="feature/demo",
    )

    assert context["summary"]["status"] == "PREPARED"
    assert context["summary"]["mirrorStatus"] == "FETCHED"
    assert commands[0] == ["git", "--git-dir", str(root / "mirrors" / "1.git"), "fetch", "--prune"]


def test_local_repo_context_fetches_exact_sha_and_retries_worktree(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    mirror = root / "mirrors" / "1.git"
    mirror.mkdir(parents=True)
    head_ref = "2222222222222222222222222222222222222222"
    commands: list[list[str]] = []
    worktree_attempts = 0

    def fake_run_git(args: list[str], *, token: str | None, timeout_seconds: int) -> None:
        nonlocal worktree_attempts
        commands.append(args)
        if "worktree" in args and "add" in args:
            worktree_attempts += 1
            if worktree_attempts == 1:
                raise local_repo.LocalRepoGitError("worktree", 128, "invalid reference", token)

    monkeypatch.setenv("LOCAL_REPO_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setattr(local_repo, "_run_git", fake_run_git)

    context = prepare_local_repository_context(
        project_id=1,
        task_id=102,
        repository_url="https://gitlab.example.com/demo/service.git",
        git_project_id="1001",
        head_ref=head_ref,
    )

    assert context["summary"]["status"] == "PREPARED"
    assert worktree_attempts == 2
    assert [
        "git",
        "--git-dir",
        str(mirror),
        "fetch",
        "--no-tags",
        "origin",
        head_ref,
    ] in commands


def test_local_repo_context_sanitizes_git_failure_without_raising(
    monkeypatch,
    tmp_path: Path,
) -> None:
    basic_token = base64.b64encode(b"oauth2:secret-token").decode("ascii")

    def fake_run_git(args: list[str], *, token: str | None, timeout_seconds: int) -> None:
        raise local_repo.LocalRepoGitError(
            "clone",
            128,
            "fatal: could not read from https://oauth2:secret-token@gitlab.example.com/demo/service.git "
            f"PRIVATE-TOKEN: secret-token Authorization: Basic {basic_token} raw={basic_token}",
            token,
        )

    monkeypatch.setenv("LOCAL_REPO_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("GITLAB_TOKEN", "secret-token")
    monkeypatch.setattr(local_repo, "_run_git", fake_run_git)

    context = prepare_local_repository_context(
        project_id=1,
        task_id=103,
        repository_url="https://gitlab.example.com/demo/service",
        git_project_id="1001",
        head_ref="head-sha",
    )

    reason = context["unavailableContexts"][0]["reason"]
    workspace = context["summary"]["sourceWorkspaceSummary"]
    assert context["summary"]["status"] == "UNAVAILABLE"
    assert context["summary"]["failurePhase"] == "CLONE"
    assert workspace["status"] == "UNAVAILABLE"
    assert workspace["failurePhase"] == "CLONE"
    assert workspace["remoteUrl"] == "https://gitlab.example.com/demo/service.git"
    assert workspace["mirror"]["status"] == "UNAVAILABLE"
    assert workspace["worktree"]["status"] == "SKIPPED"
    assert context["unavailableContexts"][0]["type"] == "LOCAL_REPOSITORY"
    assert "secret-token" not in reason
    assert basic_token not in reason
    assert "****" in reason
    assert "secret-token" not in str(workspace)
    assert basic_token not in str(workspace)


def test_local_repo_cleanup_removes_expired_worktrees_and_idle_mirrors(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    expired_worktree = root / "worktrees" / "old-task"
    current_worktree = root / "worktrees" / "101"
    fresh_worktree = root / "worktrees" / "fresh-task"
    expired_mirror = root / "mirrors" / "2.git"
    current_mirror = root / "mirrors" / "1.git"
    fresh_mirror = root / "mirrors" / "3.git"

    for path in [
        expired_worktree,
        current_worktree,
        fresh_worktree,
        expired_mirror,
        current_mirror,
        fresh_mirror,
    ]:
        _write_marker(path)

    old = time.time() - (3 * 24 * 60 * 60)
    os.utime(expired_worktree, (old, old))
    os.utime(expired_mirror, (old, old))

    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("LOCAL_REPO_WORKTREE_RETENTION_HOURS", "1")
    monkeypatch.setenv("LOCAL_REPO_MIRROR_RETENTION_DAYS", "1")
    monkeypatch.setenv("GITLAB_TOKEN", "secret-token")

    summary = cleanup_local_repository_workspace(current_task_id=101, current_project_id=1)

    assert summary["status"] == "COMPLETED"
    assert summary["deletedWorktreeCount"] == 1
    assert summary["deletedMirrorCount"] == 1
    assert summary["bytesDeleted"] > 0
    assert not expired_worktree.exists()
    assert current_worktree.exists()
    assert fresh_worktree.exists()
    assert not expired_mirror.exists()
    assert current_mirror.exists()
    assert fresh_mirror.exists()
    assert "secret-token" not in str(summary)
    assert str(root) not in str(summary)


def test_local_repo_cleanup_rejects_root_and_outside_delete(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()

    with pytest.raises(local_repo.LocalRepoUnavailableError):
        local_repo._safe_rmtree(root, root)

    with pytest.raises(local_repo.LocalRepoUnavailableError):
        local_repo._safe_rmtree(root, outside)


def test_local_repo_cleanup_failure_does_not_block_prepare(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    expired_worktree = root / "worktrees" / "old-task"
    _write_marker(expired_worktree)
    old = time.time() - (3 * 24 * 60 * 60)
    os.utime(expired_worktree, (old, old))

    commands: list[list[str]] = []

    def fake_safe_rmtree(_root: Path, _target: Path) -> None:
        raise PermissionError("access denied")

    monkeypatch.setenv("LOCAL_REPO_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("LOCAL_REPO_WORKTREE_RETENTION_HOURS", "1")
    monkeypatch.setenv("LOCAL_REPO_MIRROR_RETENTION_DAYS", "1")
    monkeypatch.setattr(local_repo, "_safe_rmtree", fake_safe_rmtree)
    monkeypatch.setattr(local_repo, "_run_git", lambda args, **_kwargs: commands.append(args))

    context = prepare_local_repository_context(
        project_id=1,
        task_id=101,
        repository_url="https://gitlab.example.com/demo/service",
        git_project_id="1001",
        head_ref="2222222222222222222222222222222222222222",
    )

    cleanup = context["summary"]["cleanup"]
    workspace = context["summary"]["sourceWorkspaceSummary"]
    assert context["summary"]["status"] == "PREPARED"
    assert cleanup["status"] == "PARTIAL"
    assert workspace["cleanup"]["status"] == "PARTIAL"
    assert workspace["mirror"]["status"] == "CLONED"
    assert workspace["worktree"]["status"] == "CHECKED_OUT"
    assert cleanup["errorCount"] == 1
    assert cleanup["errors"] == ["worktree cleanup failed: PermissionError"]
    assert commands


def _write_marker(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "marker.txt").write_text("cache", encoding="utf-8")
