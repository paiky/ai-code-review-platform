import json

from app.agent_review_spike.runner import (
    AGENT_MODEL,
    BASELINE_MODEL,
    RunnerConfig,
    _candidate_environment,
    _claude_command,
    main,
)


def _manifest():
    return {
        "schemaVersion": 1,
        "sandboxAttestation": {"readOnlyMount": True, "deepseekOnlyEgress": True},
        "cases": [
            {
                "id": "case-1",
                "worktree": "case-1",
                "changedFiles": ["src/service.py"],
                "verdict": "TRUE_POSITIVE",
                "expectation": "REPORT",
                "targetFinding": {
                    "filePath": "src/service.py",
                    "startLine": 1,
                    "endLine": 1,
                    "category": "CORRECTNESS",
                    "titleKeywords": ["空值"],
                },
                "baselineContext": "bounded context",
                "diff": "diff --git a/src/service.py b/src/service.py\n+value = None",
            }
        ],
    }


def test_validate_only_writes_safe_report(tmp_path):
    worktree = tmp_path / "workspaces" / "case-1" / "src"
    worktree.mkdir(parents=True)
    (worktree / "service.py").write_text("value = None\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    output_path = tmp_path / "report.json"

    exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path / "workspaces"),
            "--output",
            str(output_path),
            "--validate-only",
        ]
    )

    assert exit_code == 0
    report_text = output_path.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["status"] == "VALIDATED"
    assert report["sampleCount"] == 1
    assert report["retention"]["sourceSnippetsSaved"] is False
    assert "value = None" not in report_text
    assert "bounded context" not in report_text


def test_claude_command_disables_builtins_and_allows_only_review_mcp(tmp_path):
    case = _manifest()["cases"][0]
    command = _claude_command(case, tmp_path / "mcp.json", RunnerConfig())

    assert BASELINE_MODEL == AGENT_MODEL == "deepseek-v4-pro[1m]"
    assert command[command.index("--tools") + 1] == ""
    assert command[command.index("--permission-mode") + 1] == "dontAsk"
    assert "--strict-mcp-config" in command
    assert "mcp__review__submit_review" in command[command.index("--allowedTools") + 1]
    assert "Bash" in command[command.index("--disallowedTools") + 1]


def test_candidate_environment_does_not_forward_platform_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "secret-database")
    monkeypatch.setenv("GITLAB_TOKEN", "secret-gitlab")
    monkeypatch.setenv("HTTP_PROXY", "http://agent-egress-proxy:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://agent-egress-proxy:3128")
    monkeypatch.setenv("NO_PROXY", "backend,localhost")

    environment = _candidate_environment("deepseek-key", tmp_path)

    assert environment["ANTHROPIC_AUTH_TOKEN"] == "deepseek-key"
    assert environment["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert environment["HTTP_PROXY"] == "http://agent-egress-proxy:3128"
    assert environment["HTTPS_PROXY"] == "http://agent-egress-proxy:3128"
    assert environment["NO_PROXY"] == "backend,localhost"
    assert "DATABASE_URL" not in environment
    assert "GITLAB_TOKEN" not in environment
