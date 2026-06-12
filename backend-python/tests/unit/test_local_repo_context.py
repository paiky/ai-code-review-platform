from __future__ import annotations

import base64
from pathlib import Path

from app.review_context import local_repo
from app.review_context.local_repo import prepare_local_repository_context


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
    assert context["summary"]["status"] == "UNAVAILABLE"
    assert context["summary"]["failurePhase"] == "CLONE"
    assert context["unavailableContexts"][0]["type"] == "LOCAL_REPOSITORY"
    assert "secret-token" not in reason
    assert basic_token not in reason
    assert "****" in reason
