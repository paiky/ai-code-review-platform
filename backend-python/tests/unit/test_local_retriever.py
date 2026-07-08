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


def _db_signal() -> dict:
    return {
        "type": "DB_SQL_MAPPER_CHANGED",
        "filePath": "src/main/resources/mapper/OrderMapper.xml",
        "details": {
            "tableNames": ["t_order"],
            "fieldNames": ["legacy_code"],
            "mapperMethodNames": ["selectOrder"],
            "entityNames": ["OrderEntity"],
        },
        "requestedContextTypes": ["DB_SCHEMA_CONTEXT", "RELATED_FILE"],
    }


def _cache_signal() -> dict:
    return {
        "type": "CACHE_WRITE_DELETE_CHANGED",
        "filePath": "src/main/java/demo/OrderCacheService.java",
        "details": {
            "cacheKeys": ["order:detail:"],
            "cacheNames": ["orderCache"],
            "keyExpressions": ["cacheKey"],
            "cacheOperations": ["set", "delete", "expire"],
        },
        "requestedContextTypes": ["CACHE_USAGE_CONTEXT", "REFERENCE_SEARCH"],
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
        planner_signals=[{"type": "MQ_CONFIG_CHANGED", "requestedContextTypes": ["MQ_CONFIG_CONTEXT"]}],
    )

    assert result["status"] == "SKIPPED"
    assert result["summary"]["queryCount"] == 0
    assert result["searches"] == []
    assert result["summary"]["skippedSignalTypes"] == [{"type": "MQ_CONFIG_CHANGED", "count": 1}]


def test_local_retriever_searches_cache_key_read_write_usage(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "109" / "head"
    _write(
        worktree / "src/main/java/demo/OrderQueryService.java",
        "\n".join(
            [
                "package demo;",
                "class OrderQueryService {",
                "  Object get(Long id) {",
                "    return redisTemplate.opsForValue().get(\"order:detail:\" + id);",
                "  }",
                "}",
            ]
        ),
    )
    _write(
        worktree / "src/main/java/demo/OrderCacheService.java",
        "\n".join(
            [
                "package demo;",
                "class OrderCacheService {",
                "  void clear(String cacheKey) {",
                "    redisTemplate.delete(cacheKey);",
                "  }",
                "}",
            ]
        ),
    )
    _write(worktree / "node_modules/noisy.js", "order:detail:")
    _write(worktree / "target/Generated.java", "cacheKey")

    def fake_rg(_worktree: Path, query: str) -> str:
        if query == "order:detail:":
            return "\n".join(
                [
                    _rg_match("src/main/java/demo/OrderQueryService.java", 4),
                    _rg_match("node_modules/noisy.js", 1),
                ]
            )
        if query == "cacheKey":
            return "\n".join(
                [
                    _rg_match("src/main/java/demo/OrderCacheService.java", 4),
                    _rg_match("target/Generated.java", 1),
                ]
            )
        return ""

    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("LOCAL_CONTEXT_SNIPPET_CONTEXT_LINES", "1")
    monkeypatch.setattr(local_retriever, "_run_rg", fake_rg)

    result = retrieve_local_reference_context(
        worktree_path=worktree,
        planner_signals=[_cache_signal()],
    )

    searches = {search["query"]: search for search in result["searches"]}

    assert result["status"] == "RETRIEVED"
    assert result["summary"]["supportedSignalTypes"] == ["CACHE_WRITE_DELETE_CHANGED"]
    assert result["summary"]["skippedSignalTypes"] == []
    assert searches["order:detail:"]["cacheKeys"] == ["order:detail:"]
    assert searches["cacheKey"]["cacheKeys"] == ["cacheKey"]
    assert searches["cacheKey"]["snippets"][0]["reason"] == "CACHE_USAGE_REFERENCE"
    assert searches["cacheKey"]["snippets"][0]["path"] == "src/main/java/demo/OrderCacheService.java"
    payload = json.dumps(result, ensure_ascii=False)
    assert "node_modules" not in payload
    assert "target/Generated.java" not in payload


def test_local_retriever_searches_db_mapper_entity_references(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "108" / "head"
    _write(
        worktree / "src/main/resources/mapper/OrderMapper.xml",
        "\n".join(
            [
                "<mapper namespace=\"demo.OrderMapper\">",
                "  <select id=\"selectOrder\">select legacy_code from t_order</select>",
                "</mapper>",
            ]
        ),
    )
    _write(
        worktree / "src/main/java/demo/entity/OrderEntity.java",
        "\n".join(
            [
                "package demo.entity;",
                "class OrderEntity {",
                "  private String legacyCode;",
                "}",
            ]
        ),
    )

    def fake_rg(_worktree: Path, query: str) -> str:
        if query == "t_order":
            return _rg_match("src/main/resources/mapper/OrderMapper.xml", 2)
        if query == "legacy_code":
            return _rg_match("src/main/resources/mapper/OrderMapper.xml", 2)
        if query == "selectOrder":
            return _rg_match("src/main/resources/mapper/OrderMapper.xml", 2)
        if query == "OrderEntity":
            return _rg_match("src/main/java/demo/entity/OrderEntity.java", 2)
        return ""

    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("LOCAL_CONTEXT_SNIPPET_CONTEXT_LINES", "1")
    monkeypatch.setattr(local_retriever, "_run_rg", fake_rg)

    result = retrieve_local_reference_context(
        worktree_path=worktree,
        planner_signals=[_db_signal()],
    )

    searches = {search["query"]: search for search in result["searches"]}

    assert result["status"] == "RETRIEVED"
    assert result["summary"]["supportedSignalTypes"] == ["DB_SQL_MAPPER_CHANGED"]
    assert result["summary"]["skippedSignalTypes"] == []
    assert result["summary"]["queryCount"] == 4
    assert searches["t_order"]["tableNames"] == ["t_order"]
    assert searches["t_order"]["snippets"][0]["reason"] == "DB_SCHEMA_REFERENCE"
    assert searches["legacy_code"]["fieldNames"] == ["legacy_code"]
    assert searches["legacy_code"]["snippets"][0]["reason"] == "DB_FIELD_REFERENCE"
    assert searches["selectOrder"]["mapperMethodNames"] == ["selectOrder"]
    assert searches["selectOrder"]["snippets"][0]["reason"] == "MAPPER_METHOD_REFERENCE"
    assert searches["OrderEntity"]["entityNames"] == ["OrderEntity"]
    assert searches["OrderEntity"]["snippets"][0]["reason"] == "ENTITY_REFERENCE"


def test_local_retriever_adds_method_relation_evidence_candidates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "110" / "head"
    _write(
        worktree / "src/main/java/demo/OrderService.java",
        "\n".join(
            [
                "package demo;",
                "class OrderService {",
                "  Order cancelOrder(Long id) {",
                "    validateOrder(id);",
                "    return null;",
                "  }",
                "}",
            ]
        ),
    )
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
    _write(
        worktree / "src/main/java/demo/OrderValidator.java",
        "\n".join(
            [
                "package demo;",
                "class OrderValidator {",
                "  void validateOrder(Long id) {}",
                "}",
            ]
        ),
    )

    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setattr(
        local_retriever,
        "_run_rg",
        lambda _worktree, query: _rg_match("src/main/java/demo/OrderController.java", 4)
        if query == "cancelOrder"
        else "",
    )

    result = retrieve_local_reference_context(
        worktree_path=worktree,
        planner_signals=[_signal("METHOD_SIGNATURE_CHANGED")],
    )

    search = result["searches"][0]
    relations = {item["relation"] for item in search["evidenceCandidates"]}

    assert result["summary"]["evidenceCandidateCount"] >= 2
    assert "CONTROLLER_SERVICE" in relations
    assert "CALLEE" in relations
    assert any(item["symbol"] == "validateOrder" for item in search["evidenceCandidates"])
    assert "validateOrder(id);" not in json.dumps(search["evidenceCandidates"], ensure_ascii=False)


def test_local_retriever_adds_interface_implementation_evidence_without_rg_match(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "111" / "head"
    _write(
        worktree / "src/main/java/demo/OrderPort.java",
        "\n".join(
            [
                "package demo;",
                "interface OrderPort {",
                "  Order cancelOrder(Long id);",
                "}",
            ]
        ),
    )
    _write(
        worktree / "src/main/java/demo/OrderService.java",
        "\n".join(
            [
                "package demo;",
                "class OrderService implements OrderPort {",
                "  public Order cancelOrder(Long id) { return null; }",
                "}",
            ]
        ),
    )

    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setattr(local_retriever, "_run_rg", lambda _worktree, _query: "")

    result = retrieve_local_reference_context(
        worktree_path=worktree,
        planner_signals=[
            {
                "type": "METHOD_SIGNATURE_CHANGED",
                "filePath": "src/main/java/demo/OrderPort.java",
                "details": {"methodNames": ["cancelOrder"]},
                "requestedContextTypes": ["REFERENCE_SEARCH", "CALLER_CONTEXT"],
            }
        ],
    )

    search = result["searches"][0]
    evidence = search["evidenceCandidates"][0]

    assert result["status"] == "RETRIEVED"
    assert result["summary"]["includedSnippetCount"] == 0
    assert result["summary"]["evidenceCandidateCount"] == 1
    assert search["matchedFileCount"] == 1
    assert evidence["relation"] == "INTERFACE_IMPLEMENTATION"
    assert evidence["path"] == "src/main/java/demo/OrderService.java"
    assert evidence["symbol"] == "OrderService implements OrderPort"


def test_local_retriever_adds_mybatis_namespace_and_service_mapper_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "112" / "head"
    _write(
        worktree / "src/main/resources/mapper/OrderMapper.xml",
        "\n".join(
            [
                "<mapper namespace=\"demo.OrderMapper\">",
                "  <select id=\"selectOrder\">select * from t_order</select>",
                "</mapper>",
            ]
        ),
    )
    _write(
        worktree / "src/main/java/demo/OrderService.java",
        "\n".join(
            [
                "package demo;",
                "class OrderService {",
                "  Order find(Long id) {",
                "    return orderMapper.selectOrder(id);",
                "  }",
                "}",
            ]
        ),
    )

    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setattr(local_retriever, "_run_rg", lambda _worktree, _query: "")

    result = retrieve_local_reference_context(
        worktree_path=worktree,
        planner_signals=[_db_signal()],
    )

    searches = {search["query"]: search for search in result["searches"]}
    evidence = searches["selectOrder"]["evidenceCandidates"]
    relations = {item["relation"] for item in evidence}

    assert "MYBATIS_MAPPER_METHOD" in relations
    assert "SERVICE_MAPPER" in relations
    assert any(item["symbol"] == "demo.OrderMapper.selectOrder" for item in evidence)
    assert any(item["path"] == "src/main/java/demo/OrderService.java" for item in evidence)


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
    assert any(
        item["relation"] == "DTO_FIELD_REFERENCE"
        and item["symbol"] == "getLegacyCode"
        and item["path"] == "src/main/java/demo/web/OrderController.java"
        for item in searches["getLegacyCode"]["evidenceCandidates"]
    )


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
