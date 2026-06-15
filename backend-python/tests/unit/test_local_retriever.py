from __future__ import annotations

import json
from pathlib import Path

from app.review_context import local_retriever
from app.review_context.local_retriever import retrieve_local_reference_context


def _signal(signal_type: str, method_name: str = "cancelOrder") -> dict:
    return {
        "type": signal_type,
        "filePath": "src/main/java/demo/OrderService.java",
        "details": {"methodNames": [method_name]},
        "requestedContextTypes": ["REFERENCE_SEARCH", "CALLER_CONTEXT"],
    }


def _field_signal(signal_type: str, field_name: str = "legacyCode") -> dict:
    return {
        "type": signal_type,
        "filePath": "src/main/java/demo/dto/OrderRequestDto.java",
        "details": {"fieldNames": [field_name]},
        "requestedContextTypes": ["REFERENCE_SEARCH", "CALLER_CONTEXT"],
    }


def _rg_match(path: str, line_number: int) -> str:
    return json.dumps(
        {
            "type": "match",
            "data": {
                "path": {"text": path},
                "line_number": line_number,
            },
        },
        ensure_ascii=False,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_local_retriever_searches_method_reference_and_ignores_build_outputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "101" / "head"
    _write(
        worktree / "src/main/java/demo/OrderController.java",
        "\n".join(
            [
                "package demo;",
                "class OrderController {",
                "  void cancel(Long id) {",
                "    orderService.cancelOrder(id);",
                "  }",
                "}",
            ]
        ),
    )
    _write(worktree / "node_modules/noisy.js", "cancelOrder();")
    _write(worktree / "target/Generated.java", "cancelOrder();")

    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("LOCAL_CONTEXT_SNIPPET_CONTEXT_LINES", "1")
    monkeypatch.setattr(
        local_retriever,
        "_run_rg",
        lambda _worktree, _query: "\n".join(
            [
                _rg_match("src/main/java/demo/OrderController.java", 4),
                _rg_match("node_modules/noisy.js", 1),
                _rg_match("target/Generated.java", 1),
            ]
        ),
    )

    result = retrieve_local_reference_context(
        worktree_path=worktree,
        planner_signals=[_signal("METHOD_DELETED")],
    )

    search = result["searches"][0]
    snippet = search["snippets"][0]

    assert result["status"] == "RETRIEVED"
    assert result["summary"]["queryCount"] == 1
    assert result["summary"]["matchedFileCount"] == 1
    assert result["summary"]["includedSnippetCount"] == 1
    assert result["summary"]["truncated"] is False
    assert result["summary"]["supportedSignalTypes"] == ["METHOD_DELETED"]
    assert result["summary"]["skippedSignalTypes"] == []
    assert search["query"] == "cancelOrder"
    assert search["matchedFileCount"] == 1
    assert snippet["path"] == "src/main/java/demo/OrderController.java"
    assert snippet["matchLine"] == 4
    assert {"number": 4, "text": "    orderService.cancelOrder(id);"} in snippet["lines"]
    assert "node_modules" not in json.dumps(result, ensure_ascii=False)
    assert "target/Generated.java" not in json.dumps(result, ensure_ascii=False)


def test_local_retriever_uses_rg_fixed_string_with_dependency_excludes() -> None:
    args = local_retriever._rg_args("cancelOrder")

    assert args[0] == "rg"
    assert "--json" in args
    assert "--fixed-strings" in args
    assert ["--glob", "!**/node_modules/**"] == args[args.index("!**/node_modules/**") - 1 : args.index("!**/node_modules/**") + 1]
    assert args[-3:] == ["-e", "cancelOrder", "."]


def test_local_retriever_skips_unsupported_planner_signals(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "102" / "head"
    worktree.mkdir(parents=True)
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setattr(
        local_retriever,
        "_run_rg",
        lambda _worktree, _query: (_ for _ in ()).throw(AssertionError("rg should not run")),
    )

    result = retrieve_local_reference_context(
        worktree_path=worktree,
        planner_signals=[{"type": "DB_SQL_MAPPER_CHANGED", "requestedContextTypes": ["DB_SCHEMA_CONTEXT"]}],
    )

    assert result["status"] == "SKIPPED"
    assert result["summary"]["queryCount"] == 0
    assert result["searches"] == []
    assert result["summary"]["skippedSignalTypes"] == [{"type": "DB_SQL_MAPPER_CHANGED", "count": 1}]


def test_local_retriever_searches_dto_field_references_with_accessors(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "106" / "head"
    _write(
        worktree / "src/main/java/demo/web/OrderController.java",
        "\n".join(
            [
                "package demo.web;",
                "class OrderController {",
                "  void create(OrderRequestDto request) {",
                "    audit(request.getLegacyCode());",
                "  }",
                "}",
            ]
        ),
    )
    _write(
        worktree / "src/main/resources/mapper/OrderMapper.xml",
        "<if test=\"legacyCode != null\">and legacy_code = #{legacyCode}</if>",
    )
    _write(
        worktree / "src/main/java/demo/dto/OrderRequestDto.java",
        "class OrderRequestDto { private String legacyCode; }",
    )

    def fake_rg(_worktree: Path, query: str) -> str:
        if query == "legacyCode":
            return "\n".join(
                [
                    _rg_match("src/main/resources/mapper/OrderMapper.xml", 1),
                    _rg_match("src/main/java/demo/dto/OrderRequestDto.java", 1),
                ]
            )
        if query == "getLegacyCode":
            return _rg_match("src/main/java/demo/web/OrderController.java", 4)
        return ""

    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("LOCAL_CONTEXT_SNIPPET_CONTEXT_LINES", "1")
    monkeypatch.setattr(local_retriever, "_run_rg", fake_rg)

    result = retrieve_local_reference_context(
        worktree_path=worktree,
        planner_signals=[_field_signal("DTO_FIELD_CHANGED")],
    )

    searches = {search["query"]: search for search in result["searches"]}
    getter_snippet = searches["getLegacyCode"]["snippets"][0]

    assert result["status"] == "RETRIEVED"
    assert result["summary"]["queryCount"] == 4
    assert result["summary"]["matchedFileCount"] == 3
    assert result["summary"]["supportedSignalTypes"] == ["DTO_FIELD_CHANGED"]
    assert result["summary"]["skippedSignalTypes"] == []
    assert searches["legacyCode"]["fieldNames"] == ["legacyCode"]
    assert searches["legacyCode"]["signalTypes"] == ["DTO_FIELD_CHANGED"]
    assert searches["legacyCode"]["candidateSnippetCount"] >= searches["legacyCode"]["includedSnippetCount"]
    assert "src/main/resources/mapper/OrderMapper.xml" in searches["legacyCode"]["topMatchedPaths"]
    assert getter_snippet["reason"] == "DTO_FIELD_REFERENCE"
    assert getter_snippet["path"] == "src/main/java/demo/web/OrderController.java"
    assert {"number": 4, "text": "    audit(request.getLegacyCode());"} in getter_snippet["lines"]


def test_local_retriever_searches_deleted_field_references(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "107" / "head"
    _write(worktree / "src/main/java/demo/OrderService.java", "order.legacyCode = null;")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setattr(
        local_retriever,
        "_run_rg",
        lambda _worktree, query: _rg_match("src/main/java/demo/OrderService.java", 1)
        if query == "legacyCode"
        else "",
    )

    result = retrieve_local_reference_context(
        worktree_path=worktree,
        planner_signals=[_field_signal("FIELD_DELETED")],
    )

    first_search = result["searches"][0]
    assert result["summary"]["supportedSignalTypes"] == ["FIELD_DELETED"]
    assert first_search["query"] == "legacyCode"
    assert first_search["snippets"][0]["reason"] == "FIELD_REFERENCE"


def test_local_retriever_bounds_files_and_snippets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "103" / "head"
    _write(worktree / "src/main/java/demo/OrderController.java", "cancelOrder();")
    _write(worktree / "src/main/java/demo/OrderJob.java", "cancelOrder();")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("LOCAL_CONTEXT_MAX_MATCHED_FILES_PER_QUERY", "1")
    monkeypatch.setenv("LOCAL_CONTEXT_MAX_SNIPPETS_PER_QUERY", "1")
    monkeypatch.setattr(
        local_retriever,
        "_run_rg",
        lambda _worktree, _query: "\n".join(
            [
                _rg_match("src/main/java/demo/OrderController.java", 1),
                _rg_match("src/main/java/demo/OrderJob.java", 1),
            ]
        ),
    )

    result = retrieve_local_reference_context(
        worktree_path=worktree,
        planner_signals=[_signal("METHOD_SIGNATURE_CHANGED")],
    )

    assert result["summary"]["queryCount"] == 1
    assert result["summary"]["matchedFileCount"] == 2
    assert result["summary"]["includedSnippetCount"] == 1
    assert result["summary"]["truncated"] is True


def test_local_retriever_rejects_worktree_outside_workspace(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))

    result = retrieve_local_reference_context(
        worktree_path=outside,
        planner_signals=[_signal("METHOD_DELETED")],
    )

    assert result["status"] == "UNAVAILABLE"
    assert result["summary"]["queryCount"] == 0
    assert result["unavailableContexts"][0]["type"] == "REFERENCE_SEARCH"
