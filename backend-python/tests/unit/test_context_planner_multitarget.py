from __future__ import annotations

import pytest

from app.review_context.planner import build_planner_baseline
from app.review_context.service import build_review_context_pack


@pytest.mark.parametrize(
    ("target_type", "path", "language", "extractor_version", "coverage_mode"),
    [
        ("BACKEND", "src/OrderService.java", "JAVA", "backend-v0", "GENERIC_FALLBACK"),
        ("WEB_PC", "frontend/src/App.tsx", "TYPESCRIPT", "web-pc-v0", "GENERIC_FALLBACK"),
        ("APP_IOS", "ios/OrderView.swift", "SWIFT", "app-ios-v0", "GENERIC_FALLBACK"),
        ("APP_ANDROID", "android/Order.kt", "KOTLIN", "app-android-v0", "GENERIC_FALLBACK"),
        ("APP_CROSS_PLATFORM", "lib/order.dart", "DART", "app-cross-platform-v0", "GENERIC_FALLBACK"),
        ("GENERAL", "config/settings.yaml", "YAML", "general-v0", "GENERIC_ONLY"),
    ],
)
def test_planner_baseline_explains_each_target_type(
    target_type: str,
    path: str,
    language: str,
    extractor_version: str,
    coverage_mode: str,
) -> None:
    baseline = build_planner_baseline(
        [{"path": path, "diffText": "+ changed"}],
        target_type,
        lambda files: [{"type": "GENERIC_TEST_SIGNAL", "filePath": files[0]["path"]}],
    )

    assert baseline["targetType"] == target_type
    assert baseline["detectedLanguages"] == [language]
    assert baseline["extractorVersions"] == ["generic-v1", extractor_version]
    assert baseline["coverageSummary"]["coverageMode"] == coverage_mode
    assert baseline["coverageSummary"]["changedFileCount"] == 1
    assert baseline["coverageSummary"]["recognizedFileCount"] == 1
    assert baseline["signals"][0]["type"] == "GENERIC_TEST_SIGNAL"


def test_planner_baseline_counts_unknown_and_unsupported_languages() -> None:
    baseline = build_planner_baseline(
        [
            {"path": "frontend/src/App.tsx", "diffText": "+ changed"},
            {"path": "frontend/src/legacy.ts", "diffText": "+ changed"},
            {"path": "assets/schema.unknown", "diffText": "+ changed"},
        ],
        "WEB_PC",
        lambda _files: [],
    )

    assert baseline["detectedLanguages"] == ["TYPESCRIPT"]
    assert baseline["coverageSummary"]["recognizedFileCount"] == 2
    assert baseline["coverageSummary"]["unrecognizedFileCount"] == 1
    assert baseline["coverageSummary"]["unsupportedLanguageCounts"] == [
        {"language": "TYPESCRIPT", "count": 2}
    ]


def test_context_pack_keeps_existing_java_signals_with_multitarget_summary(monkeypatch) -> None:
    monkeypatch.setenv("REVIEW_LOCAL_REPOSITORY_ENABLED", "false")
    context = build_review_context_pack(
        None,
        project_id=1,
        changed_files=[
            {
                "path": "src/main/java/com/demo/OrderService.java",
                "diffText": (
                    "@@ -1,2 +1,1 @@\n"
                    "- public void submitOrder(String id) {}\n"
                    "+ public void submitOrder(Long id) {}\n"
                ),
            }
        ],
        diff_text=None,
        mode="DIFF_TEXT",
        target_type="BACKEND",
    )

    plan = context["contextPack"]["contextPlan"]
    assert plan["targetType"] == "BACKEND"
    assert plan["detectedLanguages"] == ["JAVA"]
    assert plan["extractorVersions"] == ["generic-v1", "backend-v0"]
    assert plan["coverageSummary"]["coverageMode"] == "GENERIC_FALLBACK"
    assert "METHOD_SIGNATURE_CHANGED" in {
        signal["type"] for signal in context["contextPack"]["plannerSignals"]
    }
    assert context["summary"]["plannerTargetType"] == "BACKEND"
    assert context["summary"]["detectedLanguages"] == ["JAVA"]


def test_invalid_target_type_falls_back_to_general() -> None:
    baseline = build_planner_baseline([], "unsupported-target", lambda _files: [])

    assert baseline["targetType"] == "GENERAL"
    assert baseline["extractorVersions"] == ["generic-v1", "general-v0"]
    assert baseline["coverageSummary"]["coverageMode"] == "GENERIC_ONLY"
