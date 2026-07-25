from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
import re
import subprocess
from time import perf_counter
from typing import Any

from app.core.config import get_settings


SUPPORTED_REFERENCE_SIGNAL_TYPES = {
    "DB_SQL_MAPPER_CHANGED",
    "CACHE_WRITE_DELETE_CHANGED",
    "METHOD_DELETED",
    "METHOD_SIGNATURE_CHANGED",
    "FIELD_DELETED",
    "DTO_FIELD_CHANGED",
}
LOCAL_REFERENCE_CONTEXT_TYPE = "REFERENCE_SEARCH"

_DEFAULT_MAX_QUERIES = 8
_DEFAULT_MAX_MATCHED_FILES_PER_QUERY = 10
_DEFAULT_MAX_SNIPPETS_PER_QUERY = 6
_DEFAULT_SNIPPET_CONTEXT_LINES = 30
_DEFAULT_MAX_SNIPPET_CHARS = 3000
_DEFAULT_MAX_TOTAL_CHARS = 12000
_DEFAULT_MAX_SEARCH_SECONDS = 30
_DEFAULT_RG_MAX_MATCHES_PER_FILE = 20
_DEFAULT_MAX_INDEX_FILES = 2000
_DEFAULT_MAX_EVIDENCE_PER_QUERY = 12
_DB_FILE_SUFFIX_TRIM_PATTERN = re.compile(r"(mapper|repository|dao|entity|model|po|do)$", re.IGNORECASE)
_JAVA_TYPE_PATTERN = re.compile(
    r"\b(?P<kind>interface|class)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s+extends\s+(?P<extends>[A-Za-z0-9_.,\s<>]+))?"
    r"(?:\s+implements\s+(?P<implements>[A-Za-z0-9_.,\s<>]+))?"
)
_JAVA_METHOD_PATTERN = re.compile(
    r"\b(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?"
    r"(?P<return>[A-Za-z_][A-Za-z0-9_<>\[\], ?.]*)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*(?:throws\s+[^{]+)?\{?"
)
_MYBATIS_NAMESPACE_PATTERN = re.compile(r"<mapper\b[^>]*\bnamespace\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
_MYBATIS_ID_PATTERN = re.compile(r"<(select|insert|update|delete)\b[^>]*\bid\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
_METHOD_CALL_PATTERN = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_DIRECT_CALL_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_JAVA_CONTROL_WORDS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "return",
    "new",
    "throw",
    "super",
    "this",
    "try",
    "synchronized",
}

_IGNORED_DIR_NAMES = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "target",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".codegraph",
}
_RG_EXCLUDE_GLOBS = (
    "!**/.git/**",
    "!**/node_modules/**",
    "!**/dist/**",
    "!**/build/**",
    "!**/target/**",
    "!**/.venv/**",
    "!**/__pycache__/**",
    "!**/.pytest_cache/**",
    "!**/.codegraph/**",
)


class LocalReferenceSearchError(Exception):
    pass


class EvidenceRelation(str, Enum):
    CALLER = "CALLER"
    CALLEE = "CALLEE"
    INTERFACE_IMPLEMENTATION = "INTERFACE_IMPLEMENTATION"
    CONTROLLER_SERVICE = "CONTROLLER_SERVICE"
    SERVICE_MAPPER = "SERVICE_MAPPER"
    MYBATIS_MAPPER_METHOD = "MYBATIS_MAPPER_METHOD"
    DTO_FIELD_REFERENCE = "DTO_FIELD_REFERENCE"
    FIELD_REFERENCE = "FIELD_REFERENCE"
    DB_SCHEMA_REFERENCE = "DB_SCHEMA_REFERENCE"
    CACHE_USAGE_REFERENCE = "CACHE_USAGE_REFERENCE"
    RG_TEXT_MATCH = "RG_TEXT_MATCH"


class EvidencePriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceSource(str, Enum):
    SOURCE_INDEX = "SOURCE_INDEX"
    RELATION_INDEX = "RELATION_INDEX"
    RG = "RG"
    MYBATIS_XML = "MYBATIS_XML"


class EvidenceBudgetHint(str, Enum):
    PROTECT = "PROTECT"
    NORMAL = "NORMAL"
    SUMMARY_ONLY = "SUMMARY_ONLY"


@dataclass(frozen=True)
class EvidenceCandidate:
    relation: EvidenceRelation | str
    path: str
    line_range: dict[str, int]
    symbol: str
    reason: str
    confidence: int
    safe_summary: str
    source: EvidenceSource | str
    priority: EvidencePriority | str = EvidencePriority.MEDIUM
    budget_hint: EvidenceBudgetHint | str = EvidenceBudgetHint.NORMAL
    signal_types: list[str] = field(default_factory=list)
    query: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation": _enum_value(self.relation),
            "path": self.path,
            "lineRange": {
                "start": int(self.line_range.get("start") or 1),
                "end": int(self.line_range.get("end") or self.line_range.get("start") or 1),
            },
            "symbol": _truncate_text(self.symbol, 120),
            "reason": _truncate_text(self.reason, 160),
            "confidence": max(min(int(self.confidence), 100), 0),
            "safeSummary": _truncate_text(self.safe_summary, 220),
            "source": _enum_value(self.source),
            "priority": _enum_value(self.priority),
            "budgetHint": _enum_value(self.budget_hint),
            "signalTypes": [str(item)[:80] for item in self.signal_types[:6]],
            "query": _truncate_text(self.query, 120),
        }


def retrieve_local_reference_context(
    *,
    worktree_path: Path | str | None,
    planner_signals: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    signals = planner_signals or []
    queries = _queries_from_signals(signals)
    max_queries = _env_int("LOCAL_CONTEXT_MAX_QUERIES", _DEFAULT_MAX_QUERIES, minimum=1)
    selected_queries = queries[:max_queries]
    truncated = len(queries) > len(selected_queries)
    if not selected_queries:
        return _result(
            "SKIPPED",
            query_count=0,
            matched_files=set(),
            searches=[],
            truncated=truncated,
            planner_signals=signals,
        )

    started = perf_counter()
    try:
        worktree = _validate_worktree_path(worktree_path)
    except LocalReferenceSearchError as exception:
        return _result(
            "UNAVAILABLE",
            query_count=0,
            matched_files=set(),
            searches=[],
            truncated=truncated,
            planner_signals=signals,
            unavailable_contexts=[
                {
                    "type": LOCAL_REFERENCE_CONTEXT_TYPE,
                    "reason": str(exception),
                }
            ],
            duration_ms=_duration_ms(started),
        )

    source_index = _build_source_index(worktree)
    searches: list[dict[str, Any]] = []
    matched_files: set[str] = set()
    unavailable_contexts: list[dict[str, Any]] = []
    for query in selected_queries:
        try:
            search, search_matched_files = _search_query(worktree, query, source_index)
        except LocalReferenceSearchError as exception:
            truncated = True
            unavailable_contexts.append(
                {
                    "type": LOCAL_REFERENCE_CONTEXT_TYPE,
                    "reason": str(exception),
                }
            )
            continue
        searches.append(search)
        matched_files.update(search_matched_files)
        truncated = truncated or bool(search.get("truncated"))

    if _enforce_total_budget(searches):
        truncated = True
    status = "RETRIEVED"
    if unavailable_contexts and searches:
        status = "PARTIAL"
    elif unavailable_contexts:
        status = "UNAVAILABLE"
    return _result(
        status,
        query_count=len(selected_queries),
        matched_files=matched_files,
        searches=searches,
        truncated=truncated,
        planner_signals=signals,
        unavailable_contexts=unavailable_contexts,
        duration_ms=_duration_ms(started),
    )


def _queries_from_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queries: dict[str, dict[str, Any]] = {}

    def add_query(
        query: str,
        *,
        signal_type: str,
        file_path: str,
        reason: str,
        field_name: str | None = None,
        table_name: str | None = None,
        mapper_method_name: str | None = None,
        entity_name: str | None = None,
        cache_key: str | None = None,
        cache_name: str | None = None,
        cache_operation: str | None = None,
    ) -> None:
        value = str(query or "").strip()
        if not value:
            return
        item = queries.setdefault(
            value,
            {
                "query": value,
                "signalTypes": set(),
                "filePaths": set(),
                "reasons": set(),
                "fieldNames": set(),
                "tableNames": set(),
                "mapperMethodNames": set(),
                "entityNames": set(),
                "cacheKeys": set(),
                "cacheNames": set(),
                "cacheOperations": set(),
            },
        )
        item["signalTypes"].add(signal_type)
        item["reasons"].add(reason)
        if file_path:
            item["filePaths"].add(file_path)
        if field_name:
            item["fieldNames"].add(field_name)
        if table_name:
            item["tableNames"].add(table_name)
        if mapper_method_name:
            item["mapperMethodNames"].add(mapper_method_name)
        if entity_name:
            item["entityNames"].add(entity_name)
        if cache_key:
            item["cacheKeys"].add(cache_key)
        if cache_name:
            item["cacheNames"].add(cache_name)
        if cache_operation:
            item["cacheOperations"].add(cache_operation)

    for signal in signals:
        signal_type = str(signal.get("type") or "").strip().upper()
        if signal_type not in SUPPORTED_REFERENCE_SIGNAL_TYPES:
            continue
        details = signal.get("details") if isinstance(signal.get("details"), dict) else {}
        file_path = str(signal.get("filePath") or "").strip()
        if signal_type == "DB_SQL_MAPPER_CHANGED":
            table_names = _safe_string_items(details.get("tableNames"))
            field_names = _safe_string_items(details.get("fieldNames") or details.get("columnNames"))
            mapper_method_names = _safe_string_items(details.get("mapperMethodNames"))
            entity_names = _safe_string_items(details.get("entityNames"))
            if not any((table_names, field_names, mapper_method_names, entity_names)):
                entity_names = _db_file_stem_queries(file_path)
            for table_name in table_names:
                add_query(
                    table_name,
                    signal_type=signal_type,
                    file_path=file_path,
                    reason="DB_SCHEMA_REFERENCE",
                    table_name=table_name,
                )
            for field_name in field_names:
                add_query(
                    field_name,
                    signal_type=signal_type,
                    file_path=file_path,
                    reason="DB_FIELD_REFERENCE",
                    field_name=field_name,
                )
            for mapper_method_name in mapper_method_names:
                add_query(
                    mapper_method_name,
                    signal_type=signal_type,
                    file_path=file_path,
                    reason="MAPPER_METHOD_REFERENCE",
                    mapper_method_name=mapper_method_name,
                )
            for entity_name in entity_names:
                add_query(
                    entity_name,
                    signal_type=signal_type,
                    file_path=file_path,
                    reason="ENTITY_REFERENCE",
                    entity_name=entity_name,
                )
            continue

        if signal_type == "CACHE_WRITE_DELETE_CHANGED":
            cache_keys = _safe_string_items(details.get("cacheKeys"))
            cache_names = _safe_string_items(details.get("cacheNames"))
            key_expressions = _safe_string_items(details.get("keyExpressions"), limit=6)
            cache_operations = _safe_string_items(details.get("cacheOperations"), limit=6)
            for cache_key in cache_keys:
                add_query(
                    cache_key,
                    signal_type=signal_type,
                    file_path=file_path,
                    reason="CACHE_USAGE_REFERENCE",
                    cache_key=cache_key,
                )
            for cache_name in cache_names:
                add_query(
                    cache_name,
                    signal_type=signal_type,
                    file_path=file_path,
                    reason="CACHE_USAGE_REFERENCE",
                    cache_name=cache_name,
                )
            for expression in key_expressions:
                add_query(
                    expression,
                    signal_type=signal_type,
                    file_path=file_path,
                    reason="CACHE_USAGE_REFERENCE",
                    cache_key=expression,
                )
            if not any((cache_keys, cache_names, key_expressions)):
                for operation in cache_operations:
                    add_query(
                        operation,
                        signal_type=signal_type,
                        file_path=file_path,
                        reason="CACHE_USAGE_REFERENCE",
                        cache_operation=operation,
                    )
            for fallback in _cache_file_stem_queries(file_path):
                add_query(
                    fallback,
                    signal_type=signal_type,
                    file_path=file_path,
                    reason="CACHE_USAGE_REFERENCE",
                )
            continue

        if signal_type in {"METHOD_DELETED", "METHOD_SIGNATURE_CHANGED"}:
            method_names = details.get("methodNames") if isinstance(details, dict) else []
            if not isinstance(method_names, list):
                continue
            for method_name in method_names:
                add_query(
                    str(method_name or ""),
                    signal_type=signal_type,
                    file_path=file_path,
                    reason="METHOD_REFERENCE",
                )
            continue

        field_names = details.get("fieldNames") if isinstance(details, dict) else []
        if not isinstance(field_names, list):
            continue
        reason = "DTO_FIELD_REFERENCE" if signal_type == "DTO_FIELD_CHANGED" else "FIELD_REFERENCE"
        fields = [str(field_name or "").strip() for field_name in field_names if str(field_name or "").strip()]
        for field_name in fields:
            add_query(
                field_name,
                signal_type=signal_type,
                file_path=file_path,
                reason=reason,
                field_name=field_name,
            )
        for field_name in fields:
            for accessor in _field_accessor_queries(field_name):
                add_query(
                    accessor,
                    signal_type=signal_type,
                    file_path=file_path,
                    reason=reason,
                    field_name=field_name,
                )
    result = []
    for item in queries.values():
        result.append(
            {
                "query": item["query"],
                "signalTypes": sorted(item["signalTypes"]),
                "filePaths": sorted(item["filePaths"]),
                "reasons": sorted(item["reasons"]),
                "fieldNames": sorted(item["fieldNames"]),
                "tableNames": sorted(item["tableNames"]),
                "mapperMethodNames": sorted(item["mapperMethodNames"]),
                "entityNames": sorted(item["entityNames"]),
                "cacheKeys": sorted(item["cacheKeys"]),
                "cacheNames": sorted(item["cacheNames"]),
                "cacheOperations": sorted(item["cacheOperations"]),
            }
        )
    return result


def _safe_string_items(value: Any, *, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text or text in result:
            continue
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _db_file_stem_queries(file_path: str) -> list[str]:
    stem = Path(str(file_path or "").replace("\\", "/")).stem
    if not stem:
        return []
    normalized = _DB_FILE_SUFFIX_TRIM_PATTERN.sub("", stem).strip("_-.")
    result = [stem]
    if normalized and normalized != stem:
        result.append(normalized)
    return result[:2]


def _cache_file_stem_queries(file_path: str) -> list[str]:
    stem = Path(str(file_path or "").replace("\\", "/")).stem
    if not stem:
        return []
    lower = stem.lower()
    if "cache" not in lower and "redis" not in lower:
        return []
    return [stem[:80]]


def _field_accessor_queries(field_name: str) -> list[str]:
    suffix = _field_accessor_suffix(field_name)
    if not suffix:
        return []
    return [f"get{suffix}", f"set{suffix}", f"is{suffix}"]


def _field_accessor_suffix(field_name: str) -> str:
    parts = [part for part in str(field_name or "").replace("-", "_").split("_") if part]
    if len(parts) > 1:
        return "".join(part[:1].upper() + part[1:] for part in parts if part)
    value = str(field_name or "").strip()
    if not value:
        return ""
    if len(value) > 1 and value[0].islower() and value[1].isupper():
        return value
    return value[:1].upper() + value[1:]


def _search_query(
    worktree: Path,
    query: dict[str, Any],
    source_index: dict[str, Any],
) -> tuple[dict[str, Any], set[str]]:
    output = _run_rg(worktree, str(query["query"]))
    matches = _parse_rg_matches(output, worktree)
    matched_paths = set(matches)
    max_files = _env_int(
        "LOCAL_CONTEXT_MAX_MATCHED_FILES_PER_QUERY",
        _DEFAULT_MAX_MATCHED_FILES_PER_QUERY,
        minimum=1,
    )
    max_snippets = _env_int(
        "LOCAL_CONTEXT_MAX_SNIPPETS_PER_QUERY",
        _DEFAULT_MAX_SNIPPETS_PER_QUERY,
        minimum=1,
    )
    snippets: list[dict[str, Any]] = []
    ranked_paths = _rank_paths(matches, query)
    candidate_snippet_count = 0
    for relative_path in ranked_paths[:max_files]:
        candidate_snippet_count += len(_line_windows(matches[relative_path], _line_count(worktree, relative_path)))
        if len(snippets) >= max_snippets:
            break
        snippets.extend(
            _snippets_for_file(
                worktree,
                relative_path,
                matches[relative_path],
                max_snippets=max_snippets - len(snippets),
                reason=_snippet_reason(query),
            )
        )
    evidence_candidates = _evidence_candidates_for_query(
        query=query,
        snippets=snippets,
        source_index=source_index,
    )
    matched_paths.update(candidate["path"] for candidate in evidence_candidates if candidate.get("path"))
    truncated = (
        len(matches) > max_files
        or candidate_snippet_count > len(snippets)
        or any(bool(snippet.get("truncated")) for snippet in snippets)
        or bool(evidence_candidates and len(evidence_candidates) >= _max_evidence_per_query())
    )
    search = {
        "type": "REFERENCE_SEARCH",
        "query": str(query["query"]),
        "signalTypes": query.get("signalTypes") or [],
        "filePaths": query.get("filePaths") or [],
        "fieldNames": query.get("fieldNames") or [],
        "tableNames": query.get("tableNames") or [],
        "mapperMethodNames": query.get("mapperMethodNames") or [],
        "entityNames": query.get("entityNames") or [],
        "cacheKeys": query.get("cacheKeys") or [],
        "cacheNames": query.get("cacheNames") or [],
        "cacheOperations": query.get("cacheOperations") or [],
        "matchedFileCount": len(matched_paths),
        "candidateSnippetCount": int(candidate_snippet_count),
        "candidateEvidenceCount": len(evidence_candidates),
        "includedSnippetCount": len(snippets),
        "truncated": bool(truncated),
        "topMatchedPaths": _top_matched_paths(ranked_paths, evidence_candidates),
        "evidenceCandidates": evidence_candidates,
        "snippets": snippets,
    }
    return search, matched_paths


def _build_source_index(worktree: Path) -> dict[str, Any]:
    java_files: list[dict[str, Any]] = []
    xml_files: list[dict[str, Any]] = []
    java_by_path: dict[str, dict[str, Any]] = {}
    methods_by_name: dict[str, list[dict[str, Any]]] = {}
    implementations_by_interface: dict[str, list[dict[str, Any]]] = {}
    mybatis_mappers: list[dict[str, Any]] = []
    for relative_path, file_path in _iter_source_files(worktree):
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except (OSError, UnicodeError):
            continue
        lower_path = relative_path.lower()
        if lower_path.endswith(".java"):
            java_file = _index_java_file(relative_path, lines)
            java_files.append(java_file)
            java_by_path[relative_path] = java_file
            for method in java_file.get("methods") or []:
                methods_by_name.setdefault(str(method.get("name") or ""), []).append(
                    {
                        "path": relative_path,
                        "line": int(method.get("line") or 1),
                        "className": java_file.get("typeName"),
                        "role": java_file.get("role"),
                    }
                )
            for interface_name in java_file.get("implements") or []:
                implementations_by_interface.setdefault(interface_name, []).append(java_file)
            continue
        if lower_path.endswith(".xml"):
            xml_file = {"path": relative_path, "lines": lines}
            xml_files.append(xml_file)
            mapper = _index_mybatis_mapper(relative_path, lines)
            if mapper:
                mybatis_mappers.append(mapper)
    return {
        "javaFiles": java_files,
        "xmlFiles": xml_files,
        "javaByPath": java_by_path,
        "methodsByName": methods_by_name,
        "implementationsByInterface": implementations_by_interface,
        "mybatisMappers": mybatis_mappers,
    }


def _iter_source_files(worktree: Path) -> list[tuple[str, Path]]:
    max_files = _env_int("LOCAL_CONTEXT_MAX_INDEX_FILES", _DEFAULT_MAX_INDEX_FILES, minimum=1)
    result: list[tuple[str, Path]] = []
    try:
        iterator = worktree.rglob("*")
        for file_path in iterator:
            if len(result) >= max_files:
                break
            if not file_path.is_file():
                continue
            try:
                relative_path = str(file_path.relative_to(worktree)).replace("\\", "/")
            except ValueError:
                continue
            if _is_ignored_relative_path(relative_path):
                continue
            lower_path = relative_path.lower()
            if not lower_path.endswith((".java", ".xml")):
                continue
            result.append((relative_path, file_path))
    except OSError:
        return result
    return result


def _index_java_file(relative_path: str, lines: list[str]) -> dict[str, Any]:
    text = "\n".join(lines[:2000])
    type_match = _JAVA_TYPE_PATTERN.search(text)
    kind = ""
    type_name = ""
    type_line = 1
    implements: list[str] = []
    if type_match:
        kind = str(type_match.group("kind") or "").upper()
        type_name = str(type_match.group("name") or "")
        type_line = _line_number_for_offset(text, type_match.start())
        implements = _java_type_list(type_match.group("implements"))
    return {
        "path": relative_path,
        "lines": lines,
        "kind": kind,
        "typeName": type_name,
        "typeLine": type_line,
        "implements": implements,
        "role": _java_role(relative_path, text),
        "methods": _java_methods(lines),
    }


def _java_methods(lines: list[str]) -> list[dict[str, Any]]:
    methods: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("@", "//", "*")):
            continue
        match = _JAVA_METHOD_PATTERN.search(stripped)
        if not match:
            continue
        method_name = str(match.group("name") or "")
        if method_name in _JAVA_CONTROL_WORDS:
            continue
        methods.append({"name": method_name, "line": index})
    return methods


def _index_mybatis_mapper(relative_path: str, lines: list[str]) -> dict[str, Any] | None:
    namespace = ""
    namespace_line = 1
    statements: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        namespace_match = _MYBATIS_NAMESPACE_PATTERN.search(line)
        if namespace_match:
            namespace = str(namespace_match.group(1) or "")
            namespace_line = index
        for statement_match in _MYBATIS_ID_PATTERN.finditer(line):
            statements.append(
                {
                    "operation": str(statement_match.group(1) or "").lower(),
                    "id": str(statement_match.group(2) or ""),
                    "line": index,
                }
            )
    if not namespace and not statements:
        return None
    return {
        "path": relative_path,
        "namespace": namespace,
        "namespaceLine": namespace_line,
        "statements": statements,
    }


def _line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(offset, 0)) + 1


def _java_type_list(raw_value: str | None) -> list[str]:
    result: list[str] = []
    for item in re.split(r"[,<>\s]+", str(raw_value or "")):
        value = item.strip()
        if value and value not in result:
            result.append(value)
    return result


def _java_role(relative_path: str, text: str) -> str:
    lower_path = relative_path.lower()
    if "@RestController" in text or "@Controller" in text or "controller" in lower_path:
        return "CONTROLLER"
    if "@Service" in text or "service" in lower_path:
        return "SERVICE"
    if "@Mapper" in text or "@Repository" in text or any(token in lower_path for token in ("mapper", "repository", "/dao/")):
        return "MAPPER"
    if any(token in lower_path for token in ("dto", "vo", "request", "response", "payload", "form")):
        return "DTO"
    if any(token in lower_path for token in ("entity", "/model/", "/po/", "/do/")):
        return "ENTITY"
    return "JAVA"


def _normalized_paths(paths: Any) -> set[str]:
    return {str(path or "").replace("\\", "/").strip("/") for path in paths if str(path or "").strip()}


def _matching_line_numbers(lines: list[str], token: str) -> list[tuple[int, str]]:
    if not token:
        return []
    return [
        (index, line)
        for index, line in enumerate(lines, start=1)
        if token in line
    ]


def _line_has_method_call(line: str, method_name: str) -> bool:
    if not method_name:
        return False
    return bool(re.search(rf"(?:\.|\b){re.escape(method_name)}\s*\(", line))


def _is_method_declaration_line(line: str, method_name: str) -> bool:
    match = _JAVA_METHOD_PATTERN.search(line.strip())
    return bool(match and str(match.group("name") or "") == method_name)


def _called_method_names_in_body(lines: list[str], method_line: int) -> list[str]:
    result: list[str] = []
    start_index = max(method_line - 1, 0)
    brace_depth = 0
    seen_open = False
    for line in lines[start_index : start_index + 160]:
        if "{" in line:
            seen_open = True
        if seen_open:
            if _JAVA_METHOD_PATTERN.search(line.strip()):
                brace_depth += line.count("{") - line.count("}")
                continue
            for name in [*_METHOD_CALL_PATTERN.findall(line), *_DIRECT_CALL_PATTERN.findall(line)]:
                if name in _JAVA_CONTROL_WORDS or name in result:
                    continue
                result.append(name)
                if len(result) >= 12:
                    return result
        brace_depth += line.count("{") - line.count("}")
        if seen_open and brace_depth <= 0:
            break
    return result


def _top_matched_paths(ranked_paths: list[str], evidence_candidates: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for path in [
        *ranked_paths,
        *(str(candidate.get("path") or "") for candidate in evidence_candidates),
    ]:
        if path and path not in result:
            result.append(path)
        if len(result) >= 5:
            break
    return result


def _evidence_candidates_for_query(
    *,
    query: dict[str, Any],
    snippets: list[dict[str, Any]],
    source_index: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[EvidenceCandidate] = []
    candidates.extend(_relation_index_candidates(query, source_index))
    candidates.extend(_rg_evidence_candidates(query, snippets))
    return [candidate.to_dict() for candidate in _dedupe_evidence_candidates(candidates)[:_max_evidence_per_query()]]


def _relation_index_candidates(query: dict[str, Any], source_index: dict[str, Any]) -> list[EvidenceCandidate]:
    reason = _snippet_reason(query)
    candidates: list[EvidenceCandidate] = []
    if reason == "METHOD_REFERENCE":
        candidates.extend(_method_caller_candidates(query, source_index))
        candidates.extend(_method_callee_candidates(query, source_index))
        candidates.extend(_interface_implementation_candidates(query, source_index))
    if reason in {"MAPPER_METHOD_REFERENCE", "DB_SCHEMA_REFERENCE", "DB_FIELD_REFERENCE", "ENTITY_REFERENCE"}:
        candidates.extend(_mybatis_relation_candidates(query, source_index))
        candidates.extend(_service_mapper_candidates(query, source_index))
    if reason in {"DTO_FIELD_REFERENCE", "FIELD_REFERENCE"}:
        candidates.extend(_field_relation_candidates(query, source_index, relation_reason=reason))
    return candidates


def _rg_evidence_candidates(query: dict[str, Any], snippets: list[dict[str, Any]]) -> list[EvidenceCandidate]:
    candidates: list[EvidenceCandidate] = []
    relation = _relation_for_reason(_snippet_reason(query), "")
    signal_types = [str(item) for item in query.get("signalTypes") or []]
    for snippet in snippets:
        path = str(snippet.get("path") or "")
        relation_for_path = _relation_for_reason(str(snippet.get("reason") or _snippet_reason(query)), path)
        candidates.append(
            EvidenceCandidate(
                relation=relation_for_path or relation,
                path=path,
                line_range={
                    "start": int(snippet.get("startLine") or snippet.get("matchLine") or 1),
                    "end": int(snippet.get("endLine") or snippet.get("matchLine") or 1),
                },
                symbol=str(query.get("query") or ""),
                reason=str(snippet.get("reason") or _snippet_reason(query)),
                confidence=72,
                safe_summary=f"{_enum_value(relation_for_path or relation)} evidence for {query.get('query')} in {path}:{snippet.get('matchLine') or snippet.get('startLine')}",
                source=EvidenceSource.RG,
                priority=_priority_for_relation(relation_for_path or relation),
                budget_hint=_budget_hint_for_relation(relation_for_path or relation),
                signal_types=signal_types,
                query=str(query.get("query") or ""),
            )
        )
    return candidates


def _method_caller_candidates(query: dict[str, Any], source_index: dict[str, Any]) -> list[EvidenceCandidate]:
    method_name = str(query.get("query") or "").strip()
    if not method_name:
        return []
    signal_types = [str(item) for item in query.get("signalTypes") or []]
    candidates: list[EvidenceCandidate] = []
    for java_file in source_index.get("javaFiles") or []:
        relative_path = str(java_file.get("path") or "")
        for line_number, line in _matching_line_numbers(java_file.get("lines") or [], method_name):
            if _is_method_declaration_line(line, method_name):
                continue
            if not _line_has_method_call(line, method_name):
                continue
            role = str(java_file.get("role") or "")
            relation = EvidenceRelation.CONTROLLER_SERVICE if role == "CONTROLLER" else EvidenceRelation.CALLER
            candidates.append(
                _candidate(
                    relation=relation,
                    path=relative_path,
                    line_number=line_number,
                    symbol=method_name,
                    reason="METHOD_CALLER_RELATION",
                    confidence=88 if role == "CONTROLLER" else 82,
                    source=EvidenceSource.RELATION_INDEX,
                    signal_types=signal_types,
                    query=method_name,
                    safe_summary=f"{role or 'JAVA'} caller references {method_name} at {relative_path}:{line_number}",
                )
            )
    return candidates


def _method_callee_candidates(query: dict[str, Any], source_index: dict[str, Any]) -> list[EvidenceCandidate]:
    method_name = str(query.get("query") or "").strip()
    if not method_name:
        return []
    signal_types = [str(item) for item in query.get("signalTypes") or []]
    candidates: list[EvidenceCandidate] = []
    for relative_path in _normalized_paths(query.get("filePaths") or []):
        java_file = (source_index.get("javaByPath") or {}).get(relative_path)
        if not java_file:
            continue
        method = next(
            (
                item
                for item in java_file.get("methods") or []
                if str(item.get("name") or "") == method_name
            ),
            None,
        )
        if not method:
            continue
        for called_name in _called_method_names_in_body(java_file.get("lines") or [], int(method.get("line") or 1)):
            for target in (source_index.get("methodsByName") or {}).get(called_name, [])[:3]:
                candidates.append(
                    _candidate(
                        relation=EvidenceRelation.CALLEE,
                        path=str(target.get("path") or ""),
                        line_number=int(target.get("line") or 1),
                        symbol=called_name,
                        reason="METHOD_CALLEE_RELATION",
                        confidence=70,
                        source=EvidenceSource.RELATION_INDEX,
                        signal_types=signal_types,
                        query=method_name,
                        safe_summary=f"{method_name} appears to call {called_name}; declaration at {target.get('path')}:{target.get('line')}",
                    )
                )
    return candidates


def _interface_implementation_candidates(query: dict[str, Any], source_index: dict[str, Any]) -> list[EvidenceCandidate]:
    signal_types = [str(item) for item in query.get("signalTypes") or []]
    candidates: list[EvidenceCandidate] = []
    for relative_path in _normalized_paths(query.get("filePaths") or []):
        java_file = (source_index.get("javaByPath") or {}).get(relative_path)
        if not java_file or str(java_file.get("kind") or "").upper() != "INTERFACE":
            continue
        interface_name = str(java_file.get("typeName") or "")
        if not interface_name:
            continue
        for implementation in (source_index.get("implementationsByInterface") or {}).get(interface_name, []):
            candidates.append(
                _candidate(
                    relation=EvidenceRelation.INTERFACE_IMPLEMENTATION,
                    path=str(implementation.get("path") or ""),
                    line_number=int(implementation.get("typeLine") or 1),
                    symbol=f"{implementation.get('typeName')} implements {interface_name}",
                    reason="INTERFACE_IMPLEMENTATION_RELATION",
                    confidence=92,
                    source=EvidenceSource.RELATION_INDEX,
                    signal_types=signal_types,
                    query=str(query.get("query") or ""),
                    safe_summary=f"{implementation.get('typeName')} implements {interface_name} in {implementation.get('path')}:{implementation.get('typeLine')}",
                )
            )
    return candidates


def _mybatis_relation_candidates(query: dict[str, Any], source_index: dict[str, Any]) -> list[EvidenceCandidate]:
    query_value = str(query.get("query") or "").strip()
    if not query_value:
        return []
    signal_types = [str(item) for item in query.get("signalTypes") or []]
    candidates: list[EvidenceCandidate] = []
    for mapper in source_index.get("mybatisMappers") or []:
        namespace = str(mapper.get("namespace") or "")
        for statement in mapper.get("statements") or []:
            statement_id = str(statement.get("id") or "")
            if query_value not in {statement_id, namespace, namespace.split(".")[-1]}:
                continue
            candidates.append(
                _candidate(
                    relation=EvidenceRelation.MYBATIS_MAPPER_METHOD,
                    path=str(mapper.get("path") or ""),
                    line_number=int(statement.get("line") or mapper.get("namespaceLine") or 1),
                    symbol=f"{namespace}.{statement_id}" if namespace else statement_id,
                    reason="MYBATIS_NAMESPACE_ID_RELATION",
                    confidence=95,
                    source=EvidenceSource.MYBATIS_XML,
                    signal_types=signal_types,
                    query=query_value,
                    safe_summary=f"MyBatis statement {namespace}.{statement_id} is declared in {mapper.get('path')}:{statement.get('line')}",
                )
            )
    return candidates


def _service_mapper_candidates(query: dict[str, Any], source_index: dict[str, Any]) -> list[EvidenceCandidate]:
    query_value = str(query.get("query") or "").strip()
    if not query_value:
        return []
    signal_types = [str(item) for item in query.get("signalTypes") or []]
    candidates: list[EvidenceCandidate] = []
    for java_file in source_index.get("javaFiles") or []:
        if str(java_file.get("role") or "") != "SERVICE":
            continue
        relative_path = str(java_file.get("path") or "")
        for line_number, line in _matching_line_numbers(java_file.get("lines") or [], query_value):
            if not (_line_has_method_call(line, query_value) or "mapper" in line.lower()):
                continue
            candidates.append(
                _candidate(
                    relation=EvidenceRelation.SERVICE_MAPPER,
                    path=relative_path,
                    line_number=line_number,
                    symbol=query_value,
                    reason="SERVICE_MAPPER_RELATION",
                    confidence=84,
                    source=EvidenceSource.RELATION_INDEX,
                    signal_types=signal_types,
                    query=query_value,
                    safe_summary=f"Service code references mapper symbol {query_value} at {relative_path}:{line_number}",
                )
            )
    return candidates


def _field_relation_candidates(
    query: dict[str, Any],
    source_index: dict[str, Any],
    *,
    relation_reason: str,
) -> list[EvidenceCandidate]:
    query_value = str(query.get("query") or "").strip()
    if not query_value:
        return []
    signal_types = [str(item) for item in query.get("signalTypes") or []]
    relation = EvidenceRelation.DTO_FIELD_REFERENCE if relation_reason == "DTO_FIELD_REFERENCE" else EvidenceRelation.FIELD_REFERENCE
    candidates: list[EvidenceCandidate] = []
    for source_file in [*(source_index.get("javaFiles") or []), *(source_index.get("xmlFiles") or [])]:
        relative_path = str(source_file.get("path") or "")
        for line_number, line in _matching_line_numbers(source_file.get("lines") or [], query_value):
            candidates.append(
                _candidate(
                    relation=relation,
                    path=relative_path,
                    line_number=line_number,
                    symbol=query_value,
                    reason=relation_reason,
                    confidence=86 if relation == EvidenceRelation.DTO_FIELD_REFERENCE else 80,
                    source=EvidenceSource.SOURCE_INDEX,
                    signal_types=signal_types,
                    query=query_value,
                    safe_summary=f"{_enum_value(relation)} for {query_value} at {relative_path}:{line_number}",
                )
            )
    return candidates


def _relation_for_reason(reason: str, path: str) -> EvidenceRelation:
    normalized = str(reason or "").upper()
    lower_path = str(path or "").lower()
    if normalized == "MAPPER_METHOD_REFERENCE":
        return EvidenceRelation.MYBATIS_MAPPER_METHOD if lower_path.endswith(".xml") else EvidenceRelation.SERVICE_MAPPER
    if normalized in {"DB_SCHEMA_REFERENCE", "DB_FIELD_REFERENCE", "ENTITY_REFERENCE"}:
        return EvidenceRelation.DB_SCHEMA_REFERENCE
    if normalized == "CACHE_USAGE_REFERENCE":
        return EvidenceRelation.CACHE_USAGE_REFERENCE
    if normalized == "DTO_FIELD_REFERENCE":
        return EvidenceRelation.DTO_FIELD_REFERENCE
    if normalized == "FIELD_REFERENCE":
        return EvidenceRelation.FIELD_REFERENCE
    if normalized == "METHOD_REFERENCE":
        return EvidenceRelation.CONTROLLER_SERVICE if "controller" in lower_path else EvidenceRelation.CALLER
    return EvidenceRelation.RG_TEXT_MATCH


def _priority_for_relation(relation: EvidenceRelation | str) -> EvidencePriority:
    value = _enum_value(relation)
    if value in {
        EvidenceRelation.MYBATIS_MAPPER_METHOD.value,
        EvidenceRelation.CONTROLLER_SERVICE.value,
        EvidenceRelation.SERVICE_MAPPER.value,
        EvidenceRelation.INTERFACE_IMPLEMENTATION.value,
        EvidenceRelation.CALLER.value,
    }:
        return EvidencePriority.HIGH
    if value in {
        EvidenceRelation.CALLEE.value,
        EvidenceRelation.DTO_FIELD_REFERENCE.value,
        EvidenceRelation.FIELD_REFERENCE.value,
        EvidenceRelation.DB_SCHEMA_REFERENCE.value,
        EvidenceRelation.CACHE_USAGE_REFERENCE.value,
    }:
        return EvidencePriority.MEDIUM
    return EvidencePriority.LOW


def _budget_hint_for_relation(relation: EvidenceRelation | str) -> EvidenceBudgetHint:
    if _priority_for_relation(relation) == EvidencePriority.HIGH:
        return EvidenceBudgetHint.PROTECT
    return EvidenceBudgetHint.NORMAL


def _max_evidence_per_query() -> int:
    return _env_int("LOCAL_CONTEXT_MAX_EVIDENCE_PER_QUERY", _DEFAULT_MAX_EVIDENCE_PER_QUERY, minimum=1)


def _candidate(
    *,
    relation: EvidenceRelation,
    path: str,
    line_number: int,
    symbol: str,
    reason: str,
    confidence: int,
    source: EvidenceSource,
    signal_types: list[str],
    query: str,
    safe_summary: str,
) -> EvidenceCandidate:
    return EvidenceCandidate(
        relation=relation,
        path=path,
        line_range={"start": max(int(line_number), 1), "end": max(int(line_number), 1)},
        symbol=symbol,
        reason=reason,
        confidence=confidence,
        safe_summary=safe_summary,
        source=source,
        priority=_priority_for_relation(relation),
        budget_hint=_budget_hint_for_relation(relation),
        signal_types=signal_types,
        query=query,
    )


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value or "")


def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def _dedupe_evidence_candidates(candidates: list[EvidenceCandidate]) -> list[EvidenceCandidate]:
    result: list[EvidenceCandidate] = []
    seen: set[tuple[str, str, int, int, str]] = set()
    for candidate in candidates:
        start = int(candidate.line_range.get("start") or 1)
        end = int(candidate.line_range.get("end") or start)
        key = (_enum_value(candidate.relation), candidate.path, start, end, candidate.symbol)
        if not candidate.path or key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return sorted(result, key=_evidence_rank)


def _evidence_rank(candidate: EvidenceCandidate) -> tuple[int, int, str, int]:
    relation_rank = {
        EvidenceRelation.MYBATIS_MAPPER_METHOD.value: 0,
        EvidenceRelation.CONTROLLER_SERVICE.value: 1,
        EvidenceRelation.SERVICE_MAPPER.value: 2,
        EvidenceRelation.INTERFACE_IMPLEMENTATION.value: 3,
        EvidenceRelation.CALLER.value: 4,
        EvidenceRelation.CALLEE.value: 5,
        EvidenceRelation.DTO_FIELD_REFERENCE.value: 6,
        EvidenceRelation.FIELD_REFERENCE.value: 7,
        EvidenceRelation.DB_SCHEMA_REFERENCE.value: 8,
        EvidenceRelation.CACHE_USAGE_REFERENCE.value: 9,
    }.get(_enum_value(candidate.relation), 20)
    return (relation_rank, -int(candidate.confidence), candidate.path, int(candidate.line_range.get("start") or 1))


def _snippet_reason(query: dict[str, Any]) -> str:
    reasons = {str(item or "").upper() for item in query.get("reasons") or []}
    if "DB_SCHEMA_REFERENCE" in reasons:
        return "DB_SCHEMA_REFERENCE"
    if "DB_FIELD_REFERENCE" in reasons:
        return "DB_FIELD_REFERENCE"
    if "MAPPER_METHOD_REFERENCE" in reasons:
        return "MAPPER_METHOD_REFERENCE"
    if "ENTITY_REFERENCE" in reasons:
        return "ENTITY_REFERENCE"
    if "CACHE_USAGE_REFERENCE" in reasons:
        return "CACHE_USAGE_REFERENCE"
    if "DTO_FIELD_REFERENCE" in reasons:
        return "DTO_FIELD_REFERENCE"
    if "FIELD_REFERENCE" in reasons:
        return "FIELD_REFERENCE"
    return "METHOD_REFERENCE"


def _run_rg(worktree: Path, query: str) -> str:
    args = _rg_args(query)
    try:
        completed = subprocess.run(
            args,
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=_env_int("LOCAL_REPO_MAX_SEARCH_SECONDS", _DEFAULT_MAX_SEARCH_SECONDS, minimum=1),
            check=False,
        )
    except subprocess.TimeoutExpired as exception:
        raise LocalReferenceSearchError("Local reference search timed out.") from exception
    except FileNotFoundError:
        return _run_git_grep_as_rg_json(worktree, query)
    except OSError as exception:
        raise LocalReferenceSearchError(f"Local reference search cannot start: {_public_error(str(exception), worktree)}") from exception
    if completed.returncode == 1:
        return ""
    if completed.returncode != 0:
        output = completed.stderr or completed.stdout or ""
        raise LocalReferenceSearchError(f"Local reference search failed: {_public_error(output, worktree)}")
    return completed.stdout or ""


def _run_git_grep_as_rg_json(worktree: Path, query: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "grep", "-n", "-I", "-F", "-e", query, "--", "."],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=_env_int("LOCAL_REPO_MAX_SEARCH_SECONDS", _DEFAULT_MAX_SEARCH_SECONDS, minimum=1),
            check=False,
        )
    except subprocess.TimeoutExpired as exception:
        raise LocalReferenceSearchError("Local reference fallback search timed out.") from exception
    except OSError as exception:
        raise LocalReferenceSearchError(
            f"Local reference fallback search cannot start: {_public_error(str(exception), worktree)}"
        ) from exception
    if completed.returncode == 1:
        return ""
    if completed.returncode != 0:
        output = completed.stderr or completed.stdout or ""
        raise LocalReferenceSearchError(f"Local reference fallback search failed: {_public_error(output, worktree)}")

    max_per_file = _env_int(
        "LOCAL_CONTEXT_RG_MAX_MATCHES_PER_FILE",
        _DEFAULT_RG_MAX_MATCHES_PER_FILE,
        minimum=1,
    )
    counts: dict[str, int] = {}
    json_lines: list[str] = []
    for raw_line in (completed.stdout or "").splitlines():
        parts = raw_line.split(":", 2)
        if len(parts) != 3:
            continue
        relative_path, raw_line_number, line_text = parts
        try:
            line_number = max(int(raw_line_number), 1)
        except ValueError:
            continue
        normalized_path = relative_path.replace("\\", "/").removeprefix("./")
        if _is_ignored_relative_path(normalized_path):
            continue
        count = counts.get(normalized_path, 0)
        if count >= max_per_file:
            continue
        counts[normalized_path] = count + 1
        json_lines.append(
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": normalized_path},
                        "line_number": line_number,
                        "lines": {"text": f"{line_text}\n"},
                    },
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(json_lines)


def _rg_args(query: str) -> list[str]:
    args = [
        "rg",
        "--json",
        "--fixed-strings",
        "--line-number",
        "--column",
        "--color",
        "never",
        "--no-messages",
        "--max-count",
        str(_env_int("LOCAL_CONTEXT_RG_MAX_MATCHES_PER_FILE", _DEFAULT_RG_MAX_MATCHES_PER_FILE, minimum=1)),
    ]
    for glob in _RG_EXCLUDE_GLOBS:
        args.extend(["--glob", glob])
    args.extend(["-e", query, "."])
    return args


def _parse_rg_matches(output: str, worktree: Path) -> dict[str, list[int]]:
    matches: dict[str, list[int]] = {}
    for raw_line in output.splitlines():
        try:
            item = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if item.get("type") != "match":
            continue
        data = item.get("data") or {}
        relative_path = _relative_path_from_rg(data.get("path") or {}, worktree)
        line_number = data.get("line_number")
        if not relative_path or _is_ignored_relative_path(relative_path):
            continue
        try:
            number = max(int(line_number), 1)
        except (TypeError, ValueError):
            continue
        matches.setdefault(relative_path, []).append(number)
    return {path: sorted(set(lines)) for path, lines in matches.items()}


def _relative_path_from_rg(path_item: dict[str, Any], worktree: Path) -> str | None:
    raw_path = str(path_item.get("text") or "").replace("\\", "/").strip()
    if not raw_path:
        return None
    if raw_path.startswith("./"):
        raw_path = raw_path[2:]
    candidate = Path(raw_path)
    if candidate.is_absolute():
        try:
            raw_path = str(candidate.resolve(strict=False).relative_to(worktree)).replace("\\", "/")
        except ValueError:
            return None
    if raw_path.startswith("../") or "/../" in raw_path or raw_path == "..":
        return None
    return raw_path.strip("/")


def _rank_paths(matches: dict[str, list[int]], query: dict[str, Any]) -> list[str]:
    changed_paths = {str(path).replace("\\", "/").strip("/") for path in query.get("filePaths") or []}
    return sorted(matches, key=lambda path: (_path_rank(path, changed_paths), path))


def _path_rank(path: str, changed_paths: set[str]) -> int:
    lower = path.lower()
    rank = 50
    if lower in {item.lower() for item in changed_paths}:
        rank -= 10
    if lower.startswith("src/main/") or "/src/main/" in lower:
        rank -= 30
    elif lower.startswith("src/"):
        rank -= 15
    if any(token in lower for token in ("controller", "service", "mapper", "repository", "handler")):
        rank -= 10
    if any(token in lower for token in ("entity", "/dao/", "/db/", "/sql/", "migration", "migrations")):
        rank -= 9
    if lower.endswith((".xml", ".sql")):
        rank -= 6
    if any(token in lower for token in ("cache", "redis", "redisson", "caffeine", "ehcache")):
        rank -= 10
    if any(token in lower for token in ("dto", "vo", "request", "response", "payload", "form", "api", "excel")):
        rank -= 8
    if "/test/" in lower or lower.startswith("test/") or lower.startswith("tests/") or "src/test/" in lower:
        rank += 35
    if any(token in lower for token in ("generated", "snapshot", "fixture", "fixtures")):
        rank += 40
    if lower.endswith((".md", ".lock", ".log", ".min.js", ".map")):
        rank += 60
    return rank


def _snippets_for_file(
    worktree: Path,
    relative_path: str,
    match_lines: list[int],
    *,
    max_snippets: int,
    reason: str = "METHOD_REFERENCE",
) -> list[dict[str, Any]]:
    try:
        file_path = _safe_file_path(worktree, relative_path)
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, UnicodeError, LocalReferenceSearchError):
        return []
    if not lines:
        return []
    snippets: list[dict[str, Any]] = []
    for start, end, match_line in _line_windows(match_lines, len(lines))[:max_snippets]:
        snippet_lines = [{"number": number, "text": lines[number - 1]} for number in range(start, end + 1)]
        snippet = {
            "path": relative_path,
            "startLine": start,
            "endLine": end,
            "matchLine": match_line,
            "reason": reason,
            "truncated": False,
            "lines": snippet_lines,
        }
        _truncate_snippet(snippet)
        snippets.append(snippet)
    return snippets


def _line_count(worktree: Path, relative_path: str) -> int:
    try:
        file_path = _safe_file_path(worktree, relative_path)
        return len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
    except (OSError, UnicodeError, LocalReferenceSearchError):
        return 0


def _line_windows(match_lines: list[int], total_lines: int) -> list[tuple[int, int, int]]:
    context_lines = _env_int("LOCAL_CONTEXT_SNIPPET_CONTEXT_LINES", _DEFAULT_SNIPPET_CONTEXT_LINES, minimum=0)
    windows: list[tuple[int, int, int]] = []
    for match_line in sorted(set(match_lines)):
        line = min(max(match_line, 1), total_lines)
        start = max(line - context_lines, 1)
        end = min(line + context_lines, total_lines)
        if windows and start <= windows[-1][1] + 1:
            previous_start, previous_end, previous_match = windows[-1]
            windows[-1] = (previous_start, max(previous_end, end), previous_match)
            continue
        windows.append((start, end, line))
    return windows


def _truncate_snippet(snippet: dict[str, Any]) -> None:
    limit = _env_int("LOCAL_CONTEXT_MAX_SNIPPET_CHARS", _DEFAULT_MAX_SNIPPET_CHARS, minimum=200)
    while len(json.dumps(snippet, ensure_ascii=False, separators=(",", ":"))) > limit:
        lines = snippet.get("lines") or []
        if len(lines) > 1:
            lines.pop()
            snippet["lines"] = lines
            snippet["endLine"] = lines[-1]["number"]
            snippet["truncated"] = True
            continue
        if lines and len(str(lines[0].get("text") or "")) > 80:
            lines[0]["text"] = str(lines[0].get("text") or "")[:77].rstrip() + "..."
            snippet["lines"] = lines
            snippet["truncated"] = True
        break


def _enforce_total_budget(searches: list[dict[str, Any]]) -> bool:
    limit = _env_int("LOCAL_CONTEXT_MAX_TOTAL_CHARS", _DEFAULT_MAX_TOTAL_CHARS, minimum=1000)
    truncated = False
    while len(json.dumps(searches, ensure_ascii=False, separators=(",", ":"))) > limit:
        target = next((item for item in reversed(searches) if item.get("evidenceCandidates")), None)
        if target is not None:
            target["evidenceCandidates"].pop()
            target["candidateEvidenceCount"] = len(target.get("evidenceCandidates") or [])
            target["truncated"] = True
            truncated = True
            continue
        target = next((item for item in reversed(searches) if item.get("snippets")), None)
        if target is None:
            break
        target["snippets"].pop()
        target["includedSnippetCount"] = len(target.get("snippets") or [])
        target["truncated"] = True
        truncated = True
    return truncated


def _validate_worktree_path(worktree_path: Path | str | None) -> Path:
    if worktree_path is None:
        raise LocalReferenceSearchError("Task head worktree is unavailable; local reference search is skipped.")
    settings = get_settings()
    root = Path(settings.local_repo_workspace_root or ".local/review-workspaces").expanduser().resolve(strict=False)
    candidate = Path(worktree_path).expanduser().resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exception:
        raise LocalReferenceSearchError("Task head worktree escapes LOCAL_REPO_WORKSPACE_ROOT.") from exception
    if not candidate.is_dir():
        raise LocalReferenceSearchError("Task head worktree is unavailable; local reference search is skipped.")
    return candidate


def _safe_file_path(worktree: Path, relative_path: str) -> Path:
    candidate = worktree.joinpath(relative_path).resolve(strict=False)
    try:
        candidate.relative_to(worktree)
    except ValueError as exception:
        raise LocalReferenceSearchError("Matched file escapes task head worktree.") from exception
    return candidate


def _is_ignored_relative_path(relative_path: str) -> bool:
    parts = [part.lower() for part in relative_path.replace("\\", "/").split("/") if part]
    return any(part in _IGNORED_DIR_NAMES for part in parts)


def _result(
    status: str,
    *,
    query_count: int,
    matched_files: set[str],
    searches: list[dict[str, Any]],
    truncated: bool,
    planner_signals: list[dict[str, Any]],
    unavailable_contexts: list[dict[str, Any]] | None = None,
    duration_ms: int = 0,
) -> dict[str, Any]:
    included_snippet_count = sum(int(item.get("includedSnippetCount") or 0) for item in searches)
    evidence_candidate_count = sum(int(item.get("candidateEvidenceCount") or 0) for item in searches)
    supported_signal_types = _supported_signal_types(planner_signals)
    return {
        "status": status,
        "summary": {
            "queryCount": int(query_count),
            "matchedFileCount": len(matched_files),
            "includedSnippetCount": included_snippet_count,
            "evidenceCandidateCount": evidence_candidate_count,
            "truncated": bool(truncated),
            "supportedSignalTypes": supported_signal_types,
            "skippedSignalTypes": _skipped_signal_type_counts(planner_signals),
        },
        "searches": searches,
        "unavailableContexts": unavailable_contexts or [],
        "durationMs": int(duration_ms),
    }


def _supported_signal_types(signals: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(signal.get("type") or "").upper()
            for signal in signals
            if str(signal.get("type") or "").upper() in SUPPORTED_REFERENCE_SIGNAL_TYPES
        }
    )


def _skipped_signal_type_counts(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for signal in signals:
        signal_type = str(signal.get("type") or "").upper()
        if not signal_type or signal_type in SUPPORTED_REFERENCE_SIGNAL_TYPES:
            continue
        counts[signal_type] = counts.get(signal_type, 0) + 1
    return [{"type": key, "count": value} for key, value in sorted(counts.items())]


def _env_int(name: str, default: int, *, minimum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(value, minimum)


def _duration_ms(started: float) -> int:
    return max(int((perf_counter() - started) * 1000), 0)


def _public_error(value: str, worktree: Path) -> str:
    text = str(value or "").replace(str(worktree), "<task-worktree>")
    root = str(Path(get_settings().local_repo_workspace_root or ".local/review-workspaces").expanduser().resolve(strict=False))
    text = text.replace(root, "<workspace-root>")
    return text.strip()[:500] or "unknown error"
