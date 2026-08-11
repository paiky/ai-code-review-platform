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
_MAX_SAFE_VIOLATIONS = 5
_MAX_VIOLATION_COUNT = 50


class ReviewSchemaError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        violations: list[dict[str, str]] | None = None,
        violation_count: int | None = None,
    ) -> None:
        super().__init__(message)
        self.violations = list(violations or [])[:_MAX_SAFE_VIOLATIONS]
        count = len(self.violations) if violation_count is None else violation_count
        self.violation_count = min(max(int(count), 0), _MAX_VIOLATION_COUNT)
        self.violations_truncated = self.violation_count > len(self.violations)

    def safe_contract(self) -> dict[str, Any]:
        return {
            "errorCode": "REVIEW_SCHEMA_INVALID",
            "violations": self.violations,
            "violationCount": self.violation_count,
            "violationsTruncated": self.violations_truncated,
        }


class _ViolationCollector:
    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []
        self.count = 0
        self.first_message = "review card schema is invalid"

    def add(self, reason_code: str, field: str, message: str) -> None:
        if self.count == 0:
            self.first_message = message
        self.count = min(self.count + 1, _MAX_VIOLATION_COUNT)
        if len(self.items) < _MAX_SAFE_VIOLATIONS:
            self.items.append(
                {"reasonCode": reason_code, "field": str(field or "$")[:120]}
            )

    def raise_if_any(self) -> None:
        if self.count:
            raise ReviewSchemaError(
                self.first_message,
                violations=self.items,
                violation_count=self.count,
            )


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
    collector = _ViolationCollector()
    if not isinstance(card, dict):
        collector.add("CARD_SHAPE", "$", "review card must be an object")
        collector.raise_if_any()

    changed = {normalize_relative_path(item, "changedFiles") for item in changed_files}
    if not changed:
        raise ReviewSchemaError("changedFiles must not be empty")

    allowed_card_fields = {"summary", "overallLevel", "findings"}
    if any(key not in allowed_card_fields for key in card):
        collector.add("CARD_SHAPE", "$", "review card contains unsupported fields")
    summary = _collect_text(card.get("summary"), "summary", 4000, collector)
    overall_level = _collect_enum(
        card.get("overallLevel"), OVERALL_LEVELS, "overallLevel", collector
    )
    raw_findings = card.get("findings")
    if raw_findings is None:
        collector.add("REQUIRED", "findings", "findings is required")
        raw_findings = []
    elif not isinstance(raw_findings, list):
        collector.add("CARD_SHAPE", "findings", "findings must be an array")
        raw_findings = []
    elif len(raw_findings) > 50:
        collector.add("LENGTH", "findings", "findings exceeds the maximum of 50")

    findings: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for index, raw in enumerate(raw_findings[:50]):
        finding = _collect_finding(raw, changed, index, collector)
        if finding is None:
            continue
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

    collector.raise_if_any()
    if not findings:
        overall_level = "LOW"
    return {
        "summary": summary,
        "overallLevel": overall_level,
        "findings": findings,
    }


def _collect_finding(
    raw: Any,
    changed: set[str],
    index: int,
    collector: _ViolationCollector,
) -> dict[str, Any] | None:
    prefix = f"findings[{index}]"
    if not isinstance(raw, dict):
        collector.add("CARD_SHAPE", prefix, f"{prefix} must be an object")
        return None
    allowed_fields = {
        "severity", "category", "filePath", "startLine", "endLine", "title",
        "body", "suggestion", "confidence", "contextStatus", "evidence",
        "missingContext", "contextSummary",
    }
    if any(key not in allowed_fields for key in raw):
        collector.add("CARD_SHAPE", prefix, f"{prefix} contains unsupported fields")

    severity = _collect_enum(raw.get("severity"), SEVERITIES, f"{prefix}.severity", collector)
    category = _collect_text(raw.get("category"), f"{prefix}.category", 128, collector)
    if category is not None:
        category = category.upper().replace("-", "_")
    file_path = _collect_path(raw.get("filePath"), f"{prefix}.filePath", changed, collector)
    start_line = _collect_positive_int(raw.get("startLine"), f"{prefix}.startLine", collector)
    end_line = _collect_positive_int(raw.get("endLine"), f"{prefix}.endLine", collector)
    if start_line is not None and end_line is not None and end_line < start_line:
        collector.add("LINE_RANGE", f"{prefix}.endLine", f"{prefix}.endLine must be >= startLine")
    title = _collect_text(raw.get("title"), f"{prefix}.title", 500, collector)
    body = _collect_text(raw.get("body"), f"{prefix}.body", 4000, collector)
    suggestion = _collect_text(raw.get("suggestion"), f"{prefix}.suggestion", 4000, collector)
    confidence = _collect_enum(raw.get("confidence"), CONFIDENCES, f"{prefix}.confidence", collector)
    context_status = _collect_enum(
        raw.get("contextStatus"), CONTEXT_STATUSES, f"{prefix}.contextStatus", collector
    )
    evidence = _collect_text_array(raw.get("evidence"), f"{prefix}.evidence", collector)
    missing_context = _collect_text_array(
        raw.get("missingContext"), f"{prefix}.missingContext", collector
    )
    context_summary = _collect_text(
        raw.get("contextSummary"), f"{prefix}.contextSummary", 2000, collector
    )
    values = (
        severity, category, file_path, start_line, end_line, title, body,
        suggestion, confidence, context_status, evidence, missing_context,
        context_summary,
    )
    if any(value is None for value in values):
        return None
    return {
        "severity": severity,
        "category": category,
        "filePath": file_path,
        "startLine": start_line,
        "endLine": end_line,
        "title": title,
        "body": body,
        "suggestion": suggestion,
        "confidence": confidence,
        "contextStatus": context_status,
        "evidence": evidence,
        "missingContext": missing_context,
        "contextSummary": context_summary,
    }


def _collect_enum(
    value: Any, allowed: set[str], field: str, collector: _ViolationCollector
) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        collector.add("REQUIRED", field, f"{field} is required")
        return None
    if not isinstance(value, str):
        collector.add("TYPE", field, f"{field} must be a string")
        return None
    normalized = value.strip().upper()
    if normalized not in allowed:
        collector.add("ENUM", field, f"{field} has an unsupported value")
        return None
    return normalized


def _collect_positive_int(
    value: Any, field: str, collector: _ViolationCollector
) -> int | None:
    if value is None or value == "":
        collector.add("REQUIRED", field, f"{field} is required")
        return None
    if isinstance(value, bool):
        collector.add("TYPE", field, f"{field} must be a positive integer")
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        collector.add("TYPE", field, f"{field} must be a positive integer")
        return None
    if number < 1:
        collector.add("LINE_RANGE", field, f"{field} must be a positive integer")
        return None
    return number


def _collect_text(
    value: Any, field: str, max_length: int, collector: _ViolationCollector
) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        collector.add("REQUIRED", field, f"{field} must not be blank")
        return None
    if not isinstance(value, str):
        collector.add("TYPE", field, f"{field} must be a string")
        return None
    text = value.strip()
    if len(text) > max_length:
        collector.add("LENGTH", field, f"{field} exceeds the maximum length")
        return None
    return text


def _collect_path(
    value: Any, field: str, changed: set[str], collector: _ViolationCollector
) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        collector.add("REQUIRED", field, f"{field} is required")
        return None
    if not isinstance(value, str):
        collector.add("TYPE", field, f"{field} must be a string")
        return None
    try:
        path = normalize_relative_path(value, field)
    except ReviewSchemaError as exception:
        collector.add("UNSAFE_PATH", field, str(exception))
        return None
    if path not in changed:
        collector.add(
            "PATH_OUTSIDE_CHANGED_FILES", field, f"{field} is outside changedFiles"
        )
        return None
    return path


def _collect_text_array(
    value: Any, field: str, collector: _ViolationCollector
) -> list[str] | None:
    if value is None:
        collector.add("REQUIRED", field, f"{field} is required")
        return None
    if not isinstance(value, list):
        collector.add("TYPE", field, f"{field} must be an array")
        return None
    if len(value) > 20:
        collector.add("LENGTH", field, f"{field} exceeds the maximum of 20 items")
    result: list[str] = []
    valid = len(value) <= 20
    for index, item in enumerate(value[:20]):
        item_field = f"{field}[{index}]"
        if not isinstance(item, str):
            collector.add("TYPE", item_field, f"{item_field} must be a string")
            valid = False
            continue
        text = item.strip()
        if len(text) > 1000:
            collector.add("LENGTH", item_field, f"{item_field} exceeds the maximum length")
            valid = False
        elif text:
            result.append(text)
    return result if valid else None
