from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable


PlannerExtractor = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]

SUPPORTED_TARGET_TYPES = {
    "BACKEND",
    "WEB_PC",
    "APP_IOS",
    "APP_ANDROID",
    "APP_CROSS_PLATFORM",
    "GENERAL",
}

LANGUAGE_BY_SUFFIX = {
    "java": "JAVA",
    "kt": "KOTLIN",
    "kts": "KOTLIN",
    "py": "PYTHON",
    "js": "JAVASCRIPT",
    "jsx": "JAVASCRIPT",
    "ts": "TYPESCRIPT",
    "tsx": "TYPESCRIPT",
    "vue": "VUE",
    "swift": "SWIFT",
    "m": "OBJECTIVE_C",
    "mm": "OBJECTIVE_CPP",
    "dart": "DART",
    "sql": "SQL",
    "xml": "XML",
    "json": "JSON",
    "yml": "YAML",
    "yaml": "YAML",
    "properties": "PROPERTIES",
    "toml": "TOML",
    "ini": "INI",
    "conf": "CONFIG",
    "gradle": "GRADLE",
    "css": "CSS",
    "scss": "SCSS",
    "less": "LESS",
    "html": "HTML",
    "htm": "HTML",
    "sh": "SHELL",
    "bash": "SHELL",
    "md": "MARKDOWN",
}

GENERIC_SUPPORTED_LANGUAGES = {"JAVA", "SQL", "XML", "JSON", "YAML", "PROPERTIES"}


@dataclass(frozen=True)
class ExtractorSpec:
    version: str
    extractor: PlannerExtractor
    specialized: bool = False


def _empty_target_extractor(_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return []


TARGET_EXTRACTOR_REGISTRY: dict[str, ExtractorSpec] = {
    "BACKEND": ExtractorSpec("backend-v0", _empty_target_extractor),
    "WEB_PC": ExtractorSpec("web-pc-v0", _empty_target_extractor),
    "APP_IOS": ExtractorSpec("app-ios-v0", _empty_target_extractor),
    "APP_ANDROID": ExtractorSpec("app-android-v0", _empty_target_extractor),
    "APP_CROSS_PLATFORM": ExtractorSpec("app-cross-platform-v0", _empty_target_extractor),
    "GENERAL": ExtractorSpec("general-v0", _empty_target_extractor),
}


def build_planner_baseline(
    files: list[dict[str, Any]],
    target_type: str | None,
    generic_extractor: PlannerExtractor,
) -> dict[str, Any]:
    normalized_target_type = normalize_target_type(target_type)
    target_extractor = TARGET_EXTRACTOR_REGISTRY[normalized_target_type]
    signals = [*generic_extractor(files), *target_extractor.extractor(files)]
    language_counts = Counter(detect_language(str(file.get("path") or "")) for file in files)
    unknown_count = int(language_counts.pop("UNKNOWN", 0))
    detected_languages = sorted(language_counts)
    unsupported_language_counts = [
        {"language": language, "count": int(count)}
        for language, count in sorted(language_counts.items())
        if language not in GENERIC_SUPPORTED_LANGUAGES
    ]
    coverage_mode = (
        "TARGET_EXTRACTOR"
        if target_extractor.specialized
        else ("GENERIC_ONLY" if normalized_target_type == "GENERAL" else "GENERIC_FALLBACK")
    )
    return {
        "targetType": normalized_target_type,
        "detectedLanguages": detected_languages,
        "extractorVersions": ["generic-v1", target_extractor.version],
        "coverageSummary": {
            "coverageMode": coverage_mode,
            "changedFileCount": len(files),
            "recognizedFileCount": len(files) - unknown_count,
            "unrecognizedFileCount": unknown_count,
            "unsupportedLanguageCounts": unsupported_language_counts,
        },
        "signals": signals,
    }


def normalize_target_type(value: str | None) -> str:
    normalized = str(value or "GENERAL").strip().upper().replace("-", "_")
    return normalized if normalized in SUPPORTED_TARGET_TYPES else "GENERAL"


def detect_language(file_path: str) -> str:
    normalized = str(file_path or "").replace("\\", "/").lower()
    filename = normalized.rsplit("/", 1)[-1]
    if filename == "podfile":
        return "RUBY"
    if filename in {"package.json", "tsconfig.json"}:
        return "JSON"
    suffix = filename.rsplit(".", 1)[-1] if "." in filename else ""
    return LANGUAGE_BY_SUFFIX.get(suffix, "UNKNOWN")
