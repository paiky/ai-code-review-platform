from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
import re
from typing import Any


OVERALL_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
SEVERITIES = {"MINOR", "MAJOR", "CRITICAL"}
CONFIDENCES = {"LOW", "MEDIUM", "HIGH"}
CONTEXT_STATUSES = {"SUFFICIENT", "PARTIAL", "INSUFFICIENT"}
_DRIVE_PATH = re.compile(r"^[A-Za-z]:[/\\]")


class ReviewSchemaError(ValueError):
    pass


def review_card_input_schema() -> dict[str, Any]:
    return deepcopy(
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "overallLevel", "findings"],
            "properties": {
                "summary": {"type": "string"},
                "overallLevel": {
                    "type": "string",
                    "enum": sorted(OVERALL_LEVELS),
                },
                "findings": {
                    "type": "array",
                    "maxItems": 50,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "severity",
                            "category",
                            "filePath",
                            "startLine",
                            "endLine",
                            "title",
                            "body",
                            "suggestion",
                            "confidence",
                            "contextStatus",
                            "evidence",
                            "missingContext",
                            "contextSummary",
                        ],
                        "properties": {
                            "severity": {"type": "string", "enum": sorted(SEVERITIES)},
                            "category": {"type": "string", "maxLength": 128},
                            "filePath": {"type": "string"},
                            "startLine": {"type": "integer", "minimum": 1},
                            "endLine": {"type": "integer", "minimum": 1},
                            "title": {"type": "string"},
                            "body": {"type": "string"},
                            "suggestion": {"type": "string"},
                            "confidence": {"type": "string", "enum": sorted(CONFIDENCES)},
                            "contextStatus": {
                                "type": "string",
                                "enum": sorted(CONTEXT_STATUSES),
                            },
                            "evidence": {
                                "type": "array",
                                "maxItems": 20,
                                "items": {"type": "string"},
                            },
                            "missingContext": {
                                "type": "array",
                                "maxItems": 20,
                                "items": {"type": "string"},
                            },
                            "contextSummary": {"type": "string"},
                        },
                    },
                },
            },
        }
    )


def normalize_relative_path(value: Any, field: str = "path") -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        raise ReviewSchemaError(f"{field} is required")
    if text.startswith("/") or _DRIVE_PATH.match(text):
        raise ReviewSchemaError(f"{field} must be relative")
    parts = PurePosixPath(text).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ReviewSchemaError(f"{field} contains an unsafe path segment")
    return "/".join(parts)


def validate_review_card(card: Any, changed_files: list[str]) -> dict[str, Any]:
    if not isinstance(card, dict):
        raise ReviewSchemaError("review card must be an object")
    changed = {normalize_relative_path(item, "changedFiles") for item in changed_files}
    if not changed:
        raise ReviewSchemaError("changedFiles must not be empty")

    summary = _text(card.get("summary"), "summary", 4000)
    overall_level = _enum(card.get("overallLevel"), OVERALL_LEVELS, "overallLevel")
    raw_findings = card.get("findings")
    if not isinstance(raw_findings, list):
        raise ReviewSchemaError("findings must be an array")
    if len(raw_findings) > 50:
        raise ReviewSchemaError("findings exceeds the maximum of 50")

    findings: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for index, raw in enumerate(raw_findings):
        finding = _validate_finding(raw, changed, index)
        key = (
            finding["filePath"],
            finding["startLine"],
            finding["endLine"],
            finding["category"],
            finding["title"].casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        findings.append(finding)

    if not findings:
        overall_level = "LOW"
    return {
        "summary": summary,
        "overallLevel": overall_level,
        "findings": findings,
    }


def _validate_finding(raw: Any, changed: set[str], index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ReviewSchemaError(f"findings[{index}] must be an object")
    file_path = normalize_relative_path(raw.get("filePath"), f"findings[{index}].filePath")
    if file_path not in changed:
        raise ReviewSchemaError(f"findings[{index}].filePath is outside changedFiles")
    start_line = _positive_int(raw.get("startLine"), f"findings[{index}].startLine")
    end_line = _positive_int(raw.get("endLine"), f"findings[{index}].endLine")
    if end_line < start_line:
        raise ReviewSchemaError(f"findings[{index}].endLine must be >= startLine")
    return {
        "severity": _enum(raw.get("severity"), SEVERITIES, f"findings[{index}].severity"),
        "category": _text(raw.get("category"), f"findings[{index}].category", 128)
        .upper()
        .replace("-", "_"),
        "filePath": file_path,
        "startLine": start_line,
        "endLine": end_line,
        "title": _text(raw.get("title"), f"findings[{index}].title", 500),
        "body": _text(raw.get("body"), f"findings[{index}].body", 4000),
        "suggestion": _text(raw.get("suggestion"), f"findings[{index}].suggestion", 4000),
        "confidence": _enum(
            raw.get("confidence"), CONFIDENCES, f"findings[{index}].confidence"
        ),
        "contextStatus": _enum(
            raw.get("contextStatus"),
            CONTEXT_STATUSES,
            f"findings[{index}].contextStatus",
        ),
        "evidence": _text_array(raw.get("evidence"), f"findings[{index}].evidence"),
        "missingContext": _text_array(
            raw.get("missingContext"), f"findings[{index}].missingContext"
        ),
        "contextSummary": _text(
            raw.get("contextSummary"), f"findings[{index}].contextSummary", 2000
        ),
    }


def _enum(value: Any, allowed: set[str], field: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ReviewSchemaError(f"{field} has an unsupported value")
    return normalized


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ReviewSchemaError(f"{field} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exception:
        raise ReviewSchemaError(f"{field} must be a positive integer") from exception
    if number < 1:
        raise ReviewSchemaError(f"{field} must be a positive integer")
    return number


def _text(value: Any, field: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ReviewSchemaError(f"{field} must be a string")
    text = value.strip()
    if not text:
        raise ReviewSchemaError(f"{field} must not be blank")
    if len(text) > max_length:
        raise ReviewSchemaError(f"{field} exceeds the maximum length")
    return text


def _text_array(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ReviewSchemaError(f"{field} must be an array")
    if len(value) > 20:
        raise ReviewSchemaError(f"{field} exceeds the maximum of 20 items")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ReviewSchemaError(f"{field}[{index}] must be a string")
        text = item.strip()
        if len(text) > 1000:
            raise ReviewSchemaError(f"{field}[{index}] exceeds the maximum length")
        if text:
            result.append(text)
    return result
