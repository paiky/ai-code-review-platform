import json
import os
from unittest.mock import Mock

import pytest

import app.agent_review_spike.workspace as workspace_module
from app.agent_review_spike.mcp_server import ReviewMcpServer
from app.agent_review_spike.workspace import ReviewToolError, ReviewWorkspace, ToolBudget, validate_review_path


def _card():
    return {
        "summary": "未发现问题",
        "overallLevel": "LOW",
        "findings": [],
    }


def _tool_value(response):
    return json.loads(response["content"][0]["text"])


def test_workspace_lists_searches_and_reads_only_safe_files(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "service.py").write_text("one\nneedle value\nthree\n", encoding="utf-8")
    (tmp_path / ".env.production").write_text("SECRET=do-not-read", encoding="utf-8")
    dependencies = tmp_path / "node_modules"
    dependencies.mkdir()
    (dependencies / "package.js").write_text("needle secret", encoding="utf-8")
    workspace = ReviewWorkspace(tmp_path)

    listed = workspace.list_files()
    searched = workspace.search_code("needle")
    read = workspace.read_file_range("src/service.py", 2, 3)

    assert [item["path"] for item in listed["files"]] == ["src/service.py"]
    assert searched["count"] == 1
    assert searched["matches"][0]["path"] == "src/service.py"
    assert read["content"] == "2: needle value\n3: three"


@pytest.mark.parametrize("path", ["../secret.py", ".env", "keys/client.pem"])
def test_workspace_rejects_escape_and_sensitive_paths(tmp_path, path):
    (tmp_path / ".env").write_text("SECRET=x", encoding="utf-8")
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "client.pem").write_text("private", encoding="utf-8")
    workspace = ReviewWorkspace(tmp_path)

    with pytest.raises(ReviewToolError):
        workspace.read_file_range(path, 1, 1)


def test_workspace_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("symbolic links are unavailable in this test environment")

    with pytest.raises(ReviewToolError, match="symbolic links"):
        ReviewWorkspace(tmp_path).read_file_range("link.txt", 1, 1)


def test_workspace_rejects_large_binary_and_oversized_range(tmp_path):
    (tmp_path / "large.txt").write_text("x" * 20, encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"text\x00binary")
    workspace = ReviewWorkspace(tmp_path, max_file_bytes=10)

    with pytest.raises(ReviewToolError, match="maximum readable size"):
        workspace.read_file_range("large.txt", 1, 1)
    with pytest.raises(ReviewToolError, match="binary"):
        ReviewWorkspace(tmp_path).read_file_range("binary.bin", 1, 1)
    with pytest.raises(ReviewToolError, match="between"):
        ReviewWorkspace(tmp_path).read_file_range("binary.bin", 1, 401)


def test_mcp_enforces_budget_and_audit_does_not_store_source(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "service.py").write_text("UNIQUE_SOURCE_SECRET\n", encoding="utf-8")
    result_path = tmp_path / "result.json"
    audit_path = tmp_path / "audit.json"
    server = ReviewMcpServer(
        ReviewWorkspace(tmp_path),
        ["src/service.py"],
        result_path,
        audit_path,
        ToolBudget(max_calls=2, max_source_bytes=100),
    )

    read = server.call_tool(
        "read_file_range", {"path": "src/service.py", "startLine": 1, "endLine": 1}
    )
    submitted = server.call_tool("submit_review", _card())
    exhausted = server.call_tool("list_files", {})

    assert read["isError"] is False
    assert submitted["isError"] is False
    assert exhausted["isError"] is True
    assert json.loads(result_path.read_text(encoding="utf-8")) == _card()
    audit_text = audit_path.read_text(encoding="utf-8")
    assert "UNIQUE_SOURCE_SECRET" not in audit_text
    assert "src/service.py" not in audit_text
    audit = json.loads(audit_text)
    assert audit["toolCallCount"] == 2
    assert audit["sourceBytesReturned"] == len("1: UNIQUE_SOURCE_SECRET".encode("utf-8"))
    assert audit["topPathSummaries"][0]["suffix"] == ".py"
    assert audit["reviewSubmitted"] is True


def test_mcp_rejects_invalid_review_schema(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "service.py").write_text("pass\n", encoding="utf-8")
    server = ReviewMcpServer(
        ReviewWorkspace(tmp_path),
        ["src/service.py"],
        tmp_path / "result.json",
        tmp_path / "audit.json",
        ToolBudget(),
    )

    response = server.call_tool("submit_review", {"summary": "missing fields"})

    assert response["isError"] is True
    assert "REVIEW_SCHEMA_INVALID" in response["content"][0]["text"]


def test_search_rejects_high_risk_regex(tmp_path):
    (tmp_path / "source.txt").write_text("a" * 10_000, encoding="utf-8")

    with pytest.raises(ReviewToolError, match="grouped quantifiers"):
        ReviewWorkspace(tmp_path).search_code("(a|aa)+$", is_regex=True)


def test_search_returns_partial_result_when_timeout_is_reached(tmp_path, monkeypatch):
    (tmp_path / "source.txt").write_text("needle", encoding="utf-8")
    ticks = iter([0.0, 2.0])
    monkeypatch.setattr(workspace_module, "monotonic", lambda: next(ticks))

    result = ReviewWorkspace(tmp_path).search_code("needle", timeout_seconds=1)

    assert result["timedOut"] is True
    assert result["count"] == 0


def test_mcp_source_budget_counts_utf8_bytes(tmp_path):
    (tmp_path / "source.txt").write_text("中文", encoding="utf-8")
    server = ReviewMcpServer(
        ReviewWorkspace(tmp_path),
        ["source.txt"],
        tmp_path / "result.json",
        tmp_path / "audit.json",
        ToolBudget(max_source_bytes=6),
    )

    response = server.call_tool(
        "read_file_range", {"path": "source.txt", "startLine": 1, "endLine": 1}
    )

    assert response["isError"] is True
    assert "SOURCE_BUDGET_EXCEEDED" in response["content"][0]["text"]


def test_evidence_budget_converges_submits_and_reserves_submit_tool(tmp_path):
    result_path = tmp_path / "result.json"
    audit_path = tmp_path / "audit.json"
    workspace = ReviewWorkspace(tmp_path)
    workspace.list_files = Mock(wraps=workspace.list_files)
    server = ReviewMcpServer(
        workspace,
        ["source.txt"],
        result_path,
        audit_path,
        ToolBudget(),
    )

    phases = []
    for _ in range(10):
        response = server.call_tool("list_files", {})
        assert response["isError"] is False
        phases.append(_tool_value(response)["reviewBudget"])

    refused = server.call_tool("list_files", {})
    submitted = server.call_tool("submit_review", _card())
    submitted_again = server.call_tool("submit_review", _card())

    assert [item["phase"] for item in phases[:7]] == ["DISCOVERY"] * 7
    assert [item["phase"] for item in phases[7:9]] == ["CONVERGE"] * 2
    assert phases[9]["phase"] == "SUBMIT"
    assert phases[9]["mustSubmit"] is True
    assert _tool_value(refused)["errorCode"] == "EVIDENCE_COLLECTION_COMPLETE"
    assert _tool_value(refused)["reviewBudget"]["evidenceCallsUsed"] == 10
    assert workspace.list_files.call_count == 10
    assert submitted["isError"] is False
    assert submitted_again["isError"] is True
    assert _tool_value(submitted_again)["errorCode"] == "REVIEW_ALREADY_SUBMITTED"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["evidenceCallsUsed"] == 10
    assert audit["reviewSubmitted"] is True


def test_invalid_evidence_arguments_consume_an_attempt(tmp_path):
    (tmp_path / "source.txt").write_text("value\n", encoding="utf-8")
    server = ReviewMcpServer(
        ReviewWorkspace(tmp_path),
        ["source.txt"],
        tmp_path / "result.json",
        tmp_path / "audit.json",
        ToolBudget(),
    )

    response = server.call_tool(
        "read_file_range",
        {"path": "source.txt", "startLine": 0, "endLine": 1},
    )

    assert response["isError"] is True
    budget = _tool_value(response)["reviewBudget"]
    assert budget["evidenceCallsUsed"] == 1
    assert budget["evidenceCallsRemaining"] == 9


def test_read_diff_range_only_allows_changed_file_and_counts_budget(tmp_path):
    server = ReviewMcpServer(
        ReviewWorkspace(tmp_path),
        ["src/service.py"],
        tmp_path / "result.json",
        tmp_path / "audit.json",
        ToolBudget(max_calls=4, max_source_bytes=100),
        diff_by_file={"src/service.py": "@@ -1 +1 @@\n-old\n+new"},
    )

    response = server.call_tool(
        "read_diff_range",
        {"path": "src/service.py", "startLine": 1, "endLine": 2},
    )
    denied = server.call_tool(
        "read_diff_range",
        {"path": "../secret", "startLine": 1, "endLine": 1},
    )

    assert response["isError"] is False
    assert denied["isError"] is True
    audit = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
    assert audit["sourceBytesReturned"] == len("@@ -1 +1 @@\n-old".encode("utf-8"))


@pytest.mark.parametrize("path", [".env", "config/server.pem", "node_modules/a.js", "../outside.py"])
def test_changed_file_path_policy_rejects_sensitive_or_escaping_paths(path):
    with pytest.raises(ReviewToolError):
        validate_review_path(path)
