import json
from pathlib import Path
import subprocess

from app.agent_review_spike.prompting import agent_system_prompt
from app.agent_review_spike.runner import (
    AGENT_MODEL,
    BASELINE_MODEL,
    RunnerConfig,
    _candidate_cli_failure_code,
    _candidate_environment,
    _claude_command,
    _notify_progress_callback,
    _parse_claude_session,
    _run_candidate,
    _sanitize_audit_snapshot,
    main,
)
from app.agent_review.worker import _failure_message


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
    assert RunnerConfig().max_turns == 12
    assert RunnerConfig().max_tool_calls == 40
    assert RunnerConfig().max_source_bytes == 200_000
    assert RunnerConfig().timeout_seconds == 600
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
    assert environment["CLAUDE_CODE_EFFORT_LEVEL"] == "high"
    assert "DATABASE_URL" not in environment
    assert "GITLAB_TOKEN" not in environment
    assert "temperature" not in environment
    assert "top_p" not in environment
    assert "presence_penalty" not in environment
    assert "frequency_penalty" not in environment


def test_agent_prompt_requires_bounded_hypotheses_and_timely_submission():
    prompt = agent_system_prompt(_manifest()["cases"][0])

    assert "最多形成 3 个需要核实的风险假设" in prompt
    assert "不要默认调用 list_files 浏览仓库" in prompt
    assert "每个假设最多执行 1 次 search_code 和 2 次 read_file_range" in prompt
    assert "reviewBudget.phase=CONVERGE 时不得新增风险假设" in prompt
    assert "reviewBudget.mustSubmit=true 时，下一步必须调用 submit_review" in prompt
    assert "最迟在第 9 个模型决策回合调用 submit_review" in prompt
    assert "overallLevel=LOW、findings=[]" in prompt
    assert "禁止 Bash、Git、编辑、Web、其它 MCP 和子 Agent" in prompt


def test_claude_result_at_turn_budget_has_stable_failure_code():
    stdout = json.dumps(
        {
            "type": "result",
            "subtype": "error_max_turns",
            "is_error": True,
            "session_id": "session-safe-id",
            "num_turns": 13,
            "result": "raw model output must not be retained",
            "usage": {"input_tokens": 1200},
        }
    )

    session = _parse_claude_session(stdout)

    assert session == {
        "sessionId": "session-safe-id",
        "numTurns": 13,
        "usage": {"input_tokens": 1200},
        "resultSubtype": "error_max_turns",
        "isError": True,
    }
    assert "result" not in session
    assert _candidate_cli_failure_code(session, 12) == "AGENT_MAX_TURNS_EXCEEDED"
    assert (
        _failure_message("AGENT_MAX_TURNS_EXCEEDED")
        == "Agent Review reached the turn budget before submitting a Review Card"
    )


def test_non_budget_cli_failure_remains_generic():
    session = {
        "sessionId": "session-safe-id",
        "numTurns": 3,
        "resultSubtype": "error_during_execution",
        "isError": True,
    }

    assert _candidate_cli_failure_code(session, 12) == "AGENT_CLI_FAILED"
    assert (
        _failure_message("AGENT_CLI_FAILED")
        == "Claude CLI exited with a non-zero status before submitting a Review Card"
    )


def test_runner_sanitizes_and_deduplicates_progress_callbacks():
    snapshots = []
    raw = {
        "phase": "CONVERGING",
        "prompt": "SECRET_PROMPT",
        "events": [
            {
                "sequence": 1,
                "tool": "search_code",
                "status": "SUCCESS",
                "durationMs": 2,
                "itemCount": 1,
                "sourceBytes": 12,
                "query": "SECRET_QUERY",
                "queryHash": "0123456789abcdef",
                "result": "SECRET_SOURCE",
                "path": "D:/secret/source.py",
                "pathSummary": [
                    {
                        "pathHash": "fedcba9876543210",
                        "suffix": ".py",
                        "depth": 3,
                    }
                ],
                "reviewBudget": {
                    "phase": "CONVERGE",
                    "evidenceCallsUsed": 8,
                    "evidenceCallsRemaining": 2,
                    "sourceBytesRemaining": 199_988,
                    "mustSubmit": False,
                    "message": "safe fixed hint",
                },
                "assistant": "SECRET_ASSISTANT",
                "reasoning": "SECRET_REASONING",
            }
        ],
        "assistant": "SECRET_ASSISTANT",
    }
    safe = _sanitize_audit_snapshot(raw)
    state = {"sequence": -1, "phase": None}

    _notify_progress_callback(snapshots.append, safe, state)
    _notify_progress_callback(snapshots.append, safe, state)

    assert len(snapshots) == 1
    text = json.dumps(snapshots[0], ensure_ascii=False)
    assert "SECRET_" not in text
    assert "D:/secret" not in text
    assert '"query"' not in text
    assert '"message"' not in text
    assert snapshots[0]["events"][0]["queryHash"] == "0123456789abcdef"
    raw["events"] = [
        {
            **raw["events"][0],
            "sequence": sequence,
        }
        for sequence in range(1, 42)
    ]
    assert len(_sanitize_audit_snapshot(raw)["events"]) == 40


class _FakeClaudeProcess:
    def __init__(self, command, *, mode: str):
        mcp_path = Path(command[command.index("--mcp-config") + 1])
        config = json.loads(mcp_path.read_text(encoding="utf-8"))
        environment = config["mcpServers"]["review"]["env"]
        self.result_path = Path(environment["REVIEW_RESULT_PATH"])
        self.audit_path = Path(environment["REVIEW_AUDIT_PATH"])
        self.mode = mode
        self.returncode = 1 if mode == "max-turns" else 0
        self.pid = 12345

    def communicate(self, input=None, timeout=None):
        self.audit_path.write_text(
            json.dumps(
                {
                    "toolCallCount": 1,
                    "evidenceCallsUsed": 0,
                    "sourceBytesReturned": 0,
                    "diffBytesReturned": 0,
                    "blockedAccessCount": 0,
                    "reviewSubmitted": self.mode == "success",
                    "reviewBudget": {
                        "phase": "DISCOVERY",
                        "evidenceCallsUsed": 0,
                        "evidenceCallsRemaining": 10,
                        "sourceBytesRemaining": 200_000,
                        "mustSubmit": False,
                    },
                    "events": [
                        {
                            "sequence": 1,
                            "tool": "submit_review" if self.mode == "success" else "list_files",
                            "status": "SUCCESS",
                            "durationMs": 1,
                            "itemCount": 0,
                            "sourceBytes": 0,
                            "pathSummary": [],
                            "reviewBudget": {
                                "phase": "DISCOVERY",
                                "evidenceCallsUsed": 0,
                                "evidenceCallsRemaining": 10,
                                "sourceBytesRemaining": 200_000,
                                "mustSubmit": False,
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        if self.mode == "success":
            self.result_path.write_text(
                json.dumps(
                    {"summary": "未发现问题", "overallLevel": "LOW", "findings": []}
                ),
                encoding="utf-8",
            )
        event = {
            "type": "result",
            "subtype": "error_max_turns" if self.mode == "max-turns" else "success",
            "is_error": self.mode == "max-turns",
            "session_id": "safe-session",
            "num_turns": 13 if self.mode == "max-turns" else 2,
            "usage": {"input_tokens": 1},
            "result": "raw assistant output",
        }
        return json.dumps(event), "discarded stderr"

    def poll(self):
        return self.returncode


def _run_with_fake_process(tmp_path, monkeypatch, mode, callback=None, case=None):
    process = None

    def factory(command, **_kwargs):
        nonlocal process
        process = _FakeClaudeProcess(command, mode=mode)
        return process

    monkeypatch.setattr(subprocess, "Popen", factory)
    return _run_candidate(
        case or _manifest()["cases"][0],
        tmp_path,
        "fake-key",
        RunnerConfig(),
        include_card=True,
        progress_callback=callback,
    )


def test_runner_success_and_callback_failure_do_not_change_result(tmp_path, monkeypatch):
    callback_count = 0

    def failing_callback(_snapshot):
        nonlocal callback_count
        callback_count += 1
        raise RuntimeError("trace sink unavailable")

    summary = _run_with_fake_process(
        tmp_path, monkeypatch, "success", callback=failing_callback
    )

    assert summary["status"] == "SUCCESS"
    assert summary["reviewCard"]["findings"] == []
    assert callback_count == 2


def test_runner_production_case_without_target_finding_succeeds(tmp_path, monkeypatch):
    case = dict(_manifest()["cases"][0])
    case.pop("targetFinding")
    case.pop("expectation")
    case.pop("verdict")

    summary = _run_with_fake_process(
        tmp_path,
        monkeypatch,
        "success",
        case=case,
    )

    assert summary["status"] == "SUCCESS"
    assert summary["targetReported"] is False
    assert summary["reviewCard"] == {
        "summary": "未发现问题",
        "overallLevel": "LOW",
        "findings": [],
    }
    assert summary["durationMs"] >= 0
    assert summary["numTurns"] == 2


def test_runner_without_submit_keeps_stable_failure(tmp_path, monkeypatch):
    summary = _run_with_fake_process(tmp_path, monkeypatch, "not-submitted")

    assert summary["status"] == "FAILED"
    assert summary["errorCode"] == "AGENT_REVIEW_NOT_SUBMITTED"


def test_runner_turn_exhaustion_keeps_stable_failure(tmp_path, monkeypatch):
    summary = _run_with_fake_process(tmp_path, monkeypatch, "max-turns")

    assert summary["status"] == "FAILED"
    assert summary["errorCode"] == "AGENT_MAX_TURNS_EXCEEDED"
