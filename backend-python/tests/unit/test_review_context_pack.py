from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import httpx
import respx
from sqlalchemy.orm import Session

from app.review_context import local_repo
from app.review_context.service import (
    CONTEXT_PACK_MAX_CHANGED_FILES,
    CONTEXT_PACK_MAX_TOTAL_CHARS,
    build_review_context_pack,
)
from app.review_feedback.models import ReviewItemFeedback


def _enable_gitlab(monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_API_ENABLED", "true")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.test")
    monkeypatch.setenv("GITLAB_TOKEN", "unit-token")


def test_review_context_pack_summarizes_changed_files_without_diff_body() -> None:
    context = build_review_context_pack(
        None,
        project_id=1,
        mode="DIFF_TEXT",
        changed_files=[
            {
                "path": "src/OrderService.java",
                "diffText": "@@ -1,3 +1,4 @@\n package demo;\n+ order.setStatus(null);\n- oldCall();",
            }
        ],
        diff_text=None,
    )

    pack = context["contextPack"]
    first_file = pack["changedFilesSummary"]["files"][0]

    assert context["reviewContext"]["contextPack"]["version"] == "context-pack-v0"
    assert first_file["path"] == "src/OrderService.java"
    assert first_file["additions"] == 1
    assert first_file["deletions"] == 1
    assert first_file["diffContextLineCount"] == 1
    assert pack["sameFileContext"]["status"] == "PARTIAL"
    assert pack["sameFileContext"]["fullFileSourceIncluded"] is False
    assert "order.setStatus(null)" not in context["promptText"]
    assert len(context["promptText"]) <= CONTEXT_PACK_MAX_TOTAL_CHARS


@respx.mock
def test_review_context_pack_includes_bounded_same_file_source_snippet(monkeypatch) -> None:
    _enable_gitlab(monkeypatch)
    respx.get(
        "https://gitlab.example.test/api/v4/projects/1001/repository/files/src%2FOrderService.java/raw",
        params={"ref": "head-sha"},
    ).mock(
        return_value=httpx.Response(
            200,
            text="\n".join(
                [
                    "package demo;",
                    "",
                    "class OrderService {",
                    "  void prepare() {}",
                    "  void create() {",
                    "    validate();",
                    "    Order order = new Order();",
                    "    order.setStatus(null);",
                    "    save(order);",
                    "  }",
                    "}",
                ]
            ),
        )
    )

    context = build_review_context_pack(
        None,
        project_id=1,
        mode="DIFF_TEXT",
        git_project_id="1001",
        head_ref="head-sha",
        changed_files=[
            {
                "path": "src/OrderService.java",
                "diffText": (
                    "diff --git a/src/OrderService.java b/src/OrderService.java\n"
                    "@@ -5,5 +5,5 @@\n"
                    "   void create() {\n"
                    "     validate();\n"
                    "     Order order = new Order();\n"
                    "+    order.setStatus(null);\n"
                    "     save(order);\n"
                    "   }\n"
                ),
            }
        ],
        diff_text=None,
    )

    same_file = context["contextPack"]["sameFileContext"]
    snippet = same_file["sourceSnippets"][0]["snippets"][0]

    assert same_file["status"] == "AVAILABLE"
    assert same_file["availableSource"] == "GITLAB_RAW_FILE_SNIPPETS"
    assert same_file["sourceSnippetCount"] == 1
    assert snippet["changedStartLine"] == 8
    assert {"number": 8, "text": "    order.setStatus(null);"} in snippet["lines"]
    assert "order.setStatus(null)" in context["promptText"]
    assert len(context["promptText"]) <= CONTEXT_PACK_MAX_TOTAL_CHARS


def test_review_context_pack_includes_context_missing_feedback_summary(
    db_session: Session,
) -> None:
    now = datetime(2026, 6, 11, 10, 0, 0)
    db_session.add_all(
        [
            ReviewItemFeedback(
                project_id=1,
                task_id=101,
                source_type="AI_FINDING",
                item_fingerprint="finding-1",
                risk_type="TRANSACTION",
                feedback_type="FALSE_POSITIVE",
                reason_type="CONTEXT_MISSING",
                missing_context_types_json=json.dumps(["CALLER_CONTEXT", "REFERENCE_SEARCH"]),
                suggest_as_project_rule=False,
                status="PENDING",
                created_at=now,
                updated_at=now,
            ),
            ReviewItemFeedback(
                project_id=1,
                task_id=102,
                source_type="AI_FINDING",
                item_fingerprint="finding-2",
                risk_type="SECURITY",
                feedback_type="FALSE_POSITIVE",
                reason_type="CONTEXT_MISSING",
                missing_context_types_json=json.dumps(["CALLER_CONTEXT"]),
                suggest_as_project_rule=False,
                status="VALID",
                created_at=now,
                updated_at=now,
            ),
            ReviewItemFeedback(
                project_id=2,
                task_id=201,
                source_type="AI_FINDING",
                item_fingerprint="finding-other-project",
                risk_type="SECURITY",
                feedback_type="FALSE_POSITIVE",
                reason_type="CONTEXT_MISSING",
                missing_context_types_json=json.dumps(["REFERENCE_SEARCH"]),
                suggest_as_project_rule=False,
                status="PENDING",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    context = build_review_context_pack(
        db_session,
        project_id=1,
        mode="DIFF_TEXT",
        changed_files=["src/OrderService.java"],
        diff_text="diff --git a/src/OrderService.java b/src/OrderService.java\n+ public void create() {}",
    )

    summary = context["contextPack"]["contextMissingFeedbackSummary"]

    assert summary["total"] == 2
    assert {"riskType": "TRANSACTION", "count": 1} in summary["byRiskType"]
    assert {"missingContextType": "CALLER_CONTEXT", "count": 2} in summary["byMissingContextType"]
    assert context["summary"]["contextMissingFeedbackTotal"] == 2


def test_review_context_pack_builds_minimal_context_planner_signals() -> None:
    context = build_review_context_pack(
        None,
        project_id=1,
        mode="DIFF_TEXT",
        changed_files=[
            {
                "path": "src/main/java/demo/OrderService.java",
                "diffText": (
                    "diff --git a/src/main/java/demo/OrderService.java b/src/main/java/demo/OrderService.java\n"
                    "@@ -10,9 +10,8 @@\n"
                    "-    public Order cancelOrder(Long id) {\n"
                    "-        return oldCancel(id);\n"
                    "-    }\n"
                    "-    public Order createOrder(OrderRequest request) {\n"
                    "+    public Order createOrder(CreateOrderRequest request) {\n"
                    "+        redisTemplate.opsForValue().set(cacheKey, order);\n"
                    "     }\n"
                ),
            },
            {
                "path": "src/main/java/demo/dto/OrderRequestDto.java",
                "diffText": (
                    "diff --git a/src/main/java/demo/dto/OrderRequestDto.java "
                    "b/src/main/java/demo/dto/OrderRequestDto.java\n"
                    "@@ -3,6 +3,6 @@\n"
                    "-    private String legacyCode;\n"
                    "+    private String channelCode;\n"
                ),
            },
            {
                "path": "src/main/resources/mapper/OrderMapper.xml",
                "diffText": (
                    "diff --git a/src/main/resources/mapper/OrderMapper.xml "
                    "b/src/main/resources/mapper/OrderMapper.xml\n"
                    "@@ -1,3 +1,4 @@\n"
                    "+  <update id=\"touchOrder\">update t_order set updated_at = now()</update>\n"
                ),
            },
            {
                "path": "src/main/resources/application.yml",
                "diffText": (
                    "diff --git a/src/main/resources/application.yml b/src/main/resources/application.yml\n"
                    "@@ -1,3 +1,4 @@\n"
                    "+spring.kafka.consumer.group-id: order-v2\n"
                    "+feature.order-cache-enabled: true\n"
                ),
            },
        ],
        diff_text=None,
    )

    pack = context["contextPack"]
    plan = pack["contextPlan"]
    signal_types = {item["type"] for item in pack["plannerSignals"]}
    requested_types = {item["type"] for item in pack["requestedContexts"]}
    unavailable_types = {
        item["type"]
        for item in pack["unavailableContexts"]
        if item.get("requestedByPlanner")
    }

    assert plan["plannerSignalCount"] == len(pack["plannerSignals"])
    assert plan["requestedContextCount"] == len(pack["requestedContexts"])
    assert {
        "METHOD_DELETED",
        "METHOD_SIGNATURE_CHANGED",
        "FIELD_DELETED",
        "DTO_FIELD_CHANGED",
        "DB_SQL_MAPPER_CHANGED",
        "CACHE_WRITE_DELETE_CHANGED",
        "MQ_CONFIG_CHANGED",
        "CONFIG_FILE_CHANGED",
    }.issubset(signal_types)
    assert {
        "REFERENCE_SEARCH",
        "CALLER_CONTEXT",
        "RELATED_FILE",
        "DB_SCHEMA_CONTEXT",
        "CACHE_USAGE_CONTEXT",
        "MQ_CONFIG_CONTEXT",
        "CONFIG_CONTEXT",
        "TEST_RESULT_CONTEXT",
    }.issubset(requested_types)
    assert {"REFERENCE_SEARCH", "DB_SCHEMA_CONTEXT", "CONFIG_CONTEXT"}.issubset(unavailable_types)
    assert context["summary"]["plannerSignalCount"] >= 8
    assert any(item["type"] == "REFERENCE_SEARCH" for item in context["summary"]["requestedContextTypeCounts"])
    signal_counts = {item["type"]: item["count"] for item in context["summary"]["plannerSignalTypeCounts"]}
    unsupported_counts = {
        item["type"]: item["count"]
        for item in context["summary"]["retrieverUnsupportedSignalTypeCounts"]
    }
    availability = context["summary"]["requestedContextAvailability"]
    rule_gap_items = context["summary"]["ruleGapItems"]

    assert signal_counts["DTO_FIELD_CHANGED"] == 1
    assert signal_counts["METHOD_DELETED"] == 1
    assert context["summary"]["retrieverSupportedSignalTypes"] == [
        "DTO_FIELD_CHANGED",
        "FIELD_DELETED",
        "METHOD_DELETED",
        "METHOD_SIGNATURE_CHANGED",
    ]
    assert "DTO_FIELD_CHANGED" not in unsupported_counts
    assert "FIELD_DELETED" not in unsupported_counts
    assert unsupported_counts["DB_SQL_MAPPER_CHANGED"] == 1
    assert availability["unavailable"] >= 1
    assert any(item["type"] == "REFERENCE_SEARCH" for item in availability["items"])
    assert any(item["gapType"] == "UNSUPPORTED_PLANNER_SIGNAL" for item in rule_gap_items)
    assert not any(
        item["gapType"] == "UNSUPPORTED_PLANNER_SIGNAL" and item["signal"] == "DTO_FIELD_CHANGED"
        for item in rule_gap_items
    )
    assert context["summary"]["ruleGapSummary"]["total"] == len(rule_gap_items)
    for item in rule_gap_items:
        assert set(item) == {
            "gapType",
            "signal",
            "requestedContext",
            "suggestedCapability",
            "priorityReason",
        }
        assert "src/main/java" not in json.dumps(item, ensure_ascii=False)
    assert "redisTemplate.opsForValue().set" not in context["promptText"]
    assert len(context["promptText"]) <= CONTEXT_PACK_MAX_TOTAL_CHARS


def test_review_context_pack_records_local_repo_prepare_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    monkeypatch.setenv("LOCAL_REPO_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("GITLAB_TOKEN", "repo-secret")
    monkeypatch.setattr(local_repo, "_run_git", lambda args, **_kwargs: commands.append(args))

    context = build_review_context_pack(
        None,
        task_id=501,
        project_id=1,
        mode="DIFF_TEXT",
        repository_url="https://gitlab.example.com/demo/service",
        git_project_id="1001",
        head_ref="2222222222222222222222222222222222222222",
        changed_files=["src/OrderService.java"],
        diff_text="diff --git a/src/OrderService.java b/src/OrderService.java\n+ public void create() {}",
    )

    local_summary = context["contextPack"]["localRepositoryContext"]

    assert local_summary["enabled"] is True
    assert local_summary["status"] == "PREPARED"
    assert local_summary["mirrorStatus"] == "CLONED"
    assert local_summary["worktreeStatus"] == "CHECKED_OUT"
    assert context["summary"]["localRepository"]["status"] == "PREPARED"
    assert context["summary"]["localRepository"]["cleanup"]["status"] == "COMPLETED"
    assert commands
    assert "repo-secret" not in context["promptText"]
    assert str(tmp_path) not in context["promptText"]
    assert "repo-secret" not in str(context["summary"]["localRepository"]["cleanup"])
    assert str(tmp_path) not in str(context["summary"]["localRepository"]["cleanup"])


def test_review_context_pack_injects_local_reference_snippets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "503" / "head"
    commands: list[list[str]] = []

    def write_source() -> None:
        source_file = worktree / "src/main/java/demo/OrderController.java"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text(
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
            encoding="utf-8",
        )

    def fake_run_git(args: list[str], **_kwargs) -> None:
        commands.append(args)
        if "worktree" in args and "add" in args:
            write_source()

    monkeypatch.setenv("LOCAL_REPO_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("LOCAL_CONTEXT_SNIPPET_CONTEXT_LINES", "1")
    monkeypatch.setenv("GITLAB_TOKEN", "repo-secret")
    monkeypatch.setattr(local_repo, "_run_git", fake_run_git)

    context = build_review_context_pack(
        None,
        task_id=503,
        project_id=1,
        mode="DIFF_TEXT",
        repository_url="https://gitlab.example.com/demo/service",
        git_project_id="1001",
        head_ref="2222222222222222222222222222222222222222",
        changed_files=[
            {
                "path": "src/main/java/demo/OrderService.java",
                "diffText": (
                    "diff --git a/src/main/java/demo/OrderService.java "
                    "b/src/main/java/demo/OrderService.java\n"
                    "@@ -10,6 +10,3 @@\n"
                    "-    public Order cancelOrder(Long id) {\n"
                    "-        return oldCancel(id);\n"
                    "-    }\n"
                ),
            }
        ],
        diff_text=None,
    )

    retrieval = context["localReferenceRetrieval"]
    local_reference = context["contextPack"]["localReferenceContext"]
    snippet = retrieval["searches"][0]["snippets"][0]

    assert retrieval["summary"]["queryCount"] == 1
    assert retrieval["summary"]["matchedFileCount"] == 1
    assert retrieval["summary"]["includedSnippetCount"] == 1
    assert retrieval["summary"]["truncated"] is False
    assert snippet["path"] == "src/main/java/demo/OrderController.java"
    assert {"number": 4, "text": "    orderService.cancelOrder(id);"} in snippet["lines"]
    assert context["contextPack"]["localReferenceSearch"] == retrieval["summary"]
    assert local_reference["status"] == "RETRIEVED"
    assert local_reference["sourceIncluded"] is True
    assert local_reference["searches"][0]["snippets"][0]["path"] == "src/main/java/demo/OrderController.java"
    assert context["summary"]["localReferenceSearch"] == retrieval["summary"]
    assert "localReferenceContext" in context["promptText"]
    assert "orderService.cancelOrder(id)" in context["promptText"]
    assert str(tmp_path) not in context["promptText"]


def test_review_context_pack_injects_dto_field_reference_snippets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "505" / "head"
    commands: list[list[str]] = []

    def write_source() -> None:
        controller = worktree / "src/main/java/demo/web/OrderController.java"
        mapper = worktree / "src/main/resources/mapper/OrderMapper.xml"
        controller.parent.mkdir(parents=True, exist_ok=True)
        mapper.parent.mkdir(parents=True, exist_ok=True)
        controller.write_text(
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
            encoding="utf-8",
        )
        mapper.write_text(
            "<if test=\"legacyCode != null\">and legacy_code = #{legacyCode}</if>",
            encoding="utf-8",
        )

    def fake_run_git(args: list[str], **_kwargs) -> None:
        commands.append(args)
        if "worktree" in args and "add" in args:
            write_source()

    monkeypatch.setenv("LOCAL_REPO_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("LOCAL_CONTEXT_SNIPPET_CONTEXT_LINES", "1")
    monkeypatch.setenv("GITLAB_TOKEN", "repo-secret")
    monkeypatch.setattr(local_repo, "_run_git", fake_run_git)

    context = build_review_context_pack(
        None,
        task_id=505,
        project_id=1,
        mode="DIFF_TEXT",
        repository_url="https://gitlab.example.com/demo/service",
        git_project_id="1001",
        head_ref="2222222222222222222222222222222222222222",
        changed_files=[
            {
                "path": "src/main/java/demo/dto/OrderRequestDto.java",
                "diffText": (
                    "diff --git a/src/main/java/demo/dto/OrderRequestDto.java "
                    "b/src/main/java/demo/dto/OrderRequestDto.java\n"
                    "@@ -3,6 +3,6 @@\n"
                    "-    private String legacyCode;\n"
                    "+    private String channelCode;\n"
                ),
            }
        ],
        diff_text=None,
    )

    retrieval = context["localReferenceRetrieval"]
    searches = {search["query"]: search for search in retrieval["searches"]}
    local_reference = context["contextPack"]["localReferenceContext"]
    availability = context["summary"]["requestedContextAvailability"]

    assert retrieval["summary"]["supportedSignalTypes"] == ["DTO_FIELD_CHANGED", "FIELD_DELETED"]
    assert retrieval["summary"]["matchedFileCount"] >= 2
    assert searches["legacyCode"]["fieldNames"] == ["legacyCode"]
    assert searches["legacyCode"]["signalTypes"] == ["DTO_FIELD_CHANGED", "FIELD_DELETED"]
    assert searches["legacyCode"]["snippets"][0]["reason"] == "DTO_FIELD_REFERENCE"
    assert "src/main/resources/mapper/OrderMapper.xml" in searches["legacyCode"]["topMatchedPaths"]
    assert local_reference["sourceIncluded"] is True
    assert "legacyCode" in context["promptText"]
    assert searches["legacyCode"]["candidateSnippetCount"] >= searches["legacyCode"]["includedSnippetCount"]
    assert context["summary"]["localReferenceSearch"]["supportedSignalTypes"] == [
        "DTO_FIELD_CHANGED",
        "FIELD_DELETED",
    ]
    assert any(
        item["type"] == "REFERENCE_SEARCH" and item["available"] is True
        for item in availability["items"]
    )
    assert "repo-secret" not in context["promptText"]
    assert str(tmp_path) not in context["promptText"]


def test_review_context_pack_truncates_local_reference_snippets_to_fit_budget(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    worktree = root / "worktrees" / "504" / "head"
    commands: list[list[str]] = []

    def write_source() -> None:
        source_file = worktree / "src/main/java/demo/OrderController.java"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for index in range(1, 25):
            filler = "x" * 220
            if index % 4 == 0:
                lines.append(f"    orderService.cancelOrder(id); // {filler}")
            else:
                lines.append(f"    String filler{index} = \"{filler}\";")
        source_file.write_text("\n".join(lines), encoding="utf-8")

    def fake_run_git(args: list[str], **_kwargs) -> None:
        commands.append(args)
        if "worktree" in args and "add" in args:
            write_source()

    monkeypatch.setenv("LOCAL_REPO_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("LOCAL_CONTEXT_SNIPPET_CONTEXT_LINES", "0")
    monkeypatch.setenv("LOCAL_CONTEXT_MAX_SNIPPETS_PER_QUERY", "3")
    monkeypatch.setenv("GITLAB_TOKEN", "repo-secret")
    monkeypatch.setattr(local_repo, "_run_git", fake_run_git)

    context = build_review_context_pack(
        None,
        task_id=504,
        project_id=1,
        mode="DIFF_TEXT",
        repository_url="https://gitlab.example.com/demo/service",
        git_project_id="1001",
        head_ref="2222222222222222222222222222222222222222",
        changed_files=[
            {
                "path": "src/main/java/demo/OrderService.java",
                "diffText": (
                    "diff --git a/src/main/java/demo/OrderService.java "
                    "b/src/main/java/demo/OrderService.java\n"
                    "@@ -10,6 +10,3 @@\n"
                    "-    public Order cancelOrder(Long id) {\n"
                    "-        return oldCancel(id);\n"
                    "-    }\n"
                ),
            }
        ],
        diff_text=None,
    )

    local_summary = context["contextPack"]["localReferenceSearch"]
    not_injected = context["contextPack"]["notInjectedEvidence"]
    cut_detail = context["summary"]["budgetCutSummary"]["localReferenceCutDetails"][0]

    assert len(context["promptText"]) <= CONTEXT_PACK_MAX_TOTAL_CHARS
    assert local_summary["queryCount"] == 1
    assert local_summary["matchedFileCount"] == 1
    assert local_summary["truncated"] is True
    assert local_summary["includedSnippetCount"] < 3
    assert local_summary["includedSnippetCount"] >= 1
    assert not_injected["hasNotInjectedEvidence"] is True
    assert not_injected["items"][0]["signal"] == "METHOD_DELETED"
    assert not_injected["items"][0]["requestedContext"] == "REFERENCE_SEARCH"
    assert not_injected["items"][0]["querySummary"] == "cancelOrder"
    assert not_injected["items"][0]["matchedFileCount"] == 1
    assert not_injected["items"][0]["cutSnippetCount"] >= 1
    assert not_injected["items"][0]["topRelativePaths"] == ["src/main/java/demo/OrderController.java"]
    assert not_injected["items"][0]["reasonCode"] == "BUDGET_CUT"
    assert "orderService.cancelOrder" not in json.dumps(not_injected, ensure_ascii=False)
    assert "repo-secret" not in json.dumps(not_injected, ensure_ascii=False)
    assert str(tmp_path) not in json.dumps(not_injected, ensure_ascii=False)
    assert "notInjectedEvidence" in context["promptText"]
    assert "Evidence existed but was not injected" in context["promptText"]
    assert cut_detail["signal"] == "METHOD_DELETED"
    assert cut_detail["requestedContext"] == "REFERENCE_SEARCH"
    assert cut_detail["querySummary"] == "cancelOrder"
    assert cut_detail["cutSnippetCount"] >= 1
    assert "METHOD_DELETED" in context["summary"]["budgetCutSummary"]["protectedSignalTypes"]
    assert context["summary"]["budgetCutSummary"]["localReferenceMinSnippetsPerProtectedSearch"] == 1


def test_review_context_pack_marks_local_repo_failure_unavailable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_run_git(args: list[str], *, token: str | None, timeout_seconds: int) -> None:
        raise local_repo.LocalRepoGitError(
            "clone",
            128,
            "fatal: https://oauth2:repo-secret@gitlab.example.com/demo/service.git PRIVATE-TOKEN: repo-secret",
            token,
        )

    monkeypatch.setenv("LOCAL_REPO_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("LOCAL_REPO_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("GITLAB_TOKEN", "repo-secret")
    monkeypatch.setattr(local_repo, "_run_git", fake_run_git)

    context = build_review_context_pack(
        None,
        task_id=502,
        project_id=1,
        mode="DIFF_TEXT",
        repository_url="https://gitlab.example.com/demo/service",
        git_project_id="1001",
        head_ref="head-sha",
        changed_files=["src/OrderService.java"],
        diff_text="diff --git a/src/OrderService.java b/src/OrderService.java\n+ public void create() {}",
    )

    local_unavailable = next(
        item for item in context["contextPack"]["unavailableContexts"] if item["type"] == "LOCAL_REPOSITORY"
    )

    assert context["contextPack"]["localRepositoryContext"]["status"] == "UNAVAILABLE"
    assert context["summary"]["localRepository"]["status"] == "UNAVAILABLE"
    assert "repo-secret" not in local_unavailable["reason"]
    assert "repo-secret" not in context["promptText"]


def test_review_context_pack_limits_changed_file_budget() -> None:
    files = [
        {
            "path": f"src/generated/File{index:02d}.java",
            "diffText": "@@ -1 +1 @@\n-old\n+new",
        }
        for index in range(CONTEXT_PACK_MAX_CHANGED_FILES + 10)
    ]

    context = build_review_context_pack(
        None,
        project_id=1,
        mode="DIFF_TEXT",
        changed_files=files,
        diff_text=None,
    )

    changed_summary = context["contextPack"]["changedFilesSummary"]

    assert changed_summary["total"] == CONTEXT_PACK_MAX_CHANGED_FILES + 10
    assert changed_summary["included"] <= CONTEXT_PACK_MAX_CHANGED_FILES
    assert changed_summary["truncated"] is True
    assert context["meta"]["truncated"] is True
    budget_summary = context["summary"]["budgetCutSummary"]
    assert budget_summary["truncated"] is True
    assert budget_summary["changedFilesExcluded"] >= 10
    assert budget_summary["changedFilesRemovedByPromptBudget"] >= 0
    assert budget_summary["maxTotalChars"] == CONTEXT_PACK_MAX_TOTAL_CHARS
    assert len(context["promptText"]) <= CONTEXT_PACK_MAX_TOTAL_CHARS
