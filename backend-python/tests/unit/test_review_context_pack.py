from __future__ import annotations

from datetime import datetime
import json

import httpx
import respx
from sqlalchemy.orm import Session

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
    assert len(context["promptText"]) <= CONTEXT_PACK_MAX_TOTAL_CHARS
