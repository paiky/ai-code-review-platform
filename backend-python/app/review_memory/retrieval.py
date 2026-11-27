"""Bounded relational recall. Only frozen text/metadata leave this read transaction."""

from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatchcase
import hashlib
import json
import logging
import re
import unicodedata

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, undefer

from app.change_analysis.service import AGGREGATE_TYPES
from app.core.errors import AppError
from app.project_integration.schemas import TargetType
from app.review_feedback.models import ReviewItemFeedback
from app.review_memory.feedback import feedback_digest
from app.review_memory.models import (
    ReviewMemoryEntry,
    ReviewMemoryProjectSource,
    ReviewMemorySource,
)
from app.review_memory.repository import shared_source_conditions
from app.review_memory.schemas import (
    CoreBudgetItem,
    IssueType,
    MemoryEntryDraft,
    MemorySelectedSummary,
    MemorySnapshot,
)
from app.review_memory.service import render_core_context, validate_entry_for_publication
from app.review_memory.settings import read_settings


_LOGGER = logging.getLogger(__name__)
BLOCKING_MEMORY_CODES = frozenset(
    {"MEMORY_LOOKUP_FAILED", "MEMORY_CORE_BUDGET_EXCEEDED", "MEMORY_SNAPSHOT_INVALID"}
)
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,63}|[\u4e00-\u9fff]{2,16}")
_ISSUE_TERMS = {
    "DATABASE": ("sql", "select", "insert", "update", "mapper", "mybatis", "jdbc"),
    "CACHE": ("cache", "redis", "evict"),
    "MQ": ("kafka", "rabbit", "rocketmq", "producer", "consumer"),
    "TRANSACTION": ("transactional", "transaction", "aftercommit"),
    "API_CONTRACT": ("controller", "requestmapping", "responsebody", "endpoint"),
    "SECURITY": ("authorize", "permission", "authentication", "encrypt"),
    "CONFIG": ("properties", "configuration", "yaml", "config"),
    "ERROR_HANDLING": ("exception", "catch", "throw"),
    "TESTING": ("test", "assert", "mock"),
}


@dataclass(frozen=True)
class MemorySelection:
    text: str
    snapshot: MemorySnapshot


def normalized_hash(content: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", content).split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _short(value: str, limit: int = 160) -> str:
    return value.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def _labels(value: str | None) -> list[str]:
    result = json.loads(value or "[]")
    if not isinstance(result, list) or any(not isinstance(item, str) for item in result):
        raise ValueError("invalid memory labels")
    return result


def _hints(paths: list[str], diff: str, hints: list[str]) -> tuple[list[str], set[str]]:
    # Never use arbitrary context, original files, secrets from excluded paths, or whole diff as LIKE.
    path_tokens = [token.casefold() for path in paths for token in _TOKEN.findall(path[:1024])]
    diff_tokens = [token.casefold() for token in _TOKEN.findall(diff[:16000])][:512]
    tokens = path_tokens + diff_tokens
    words = list(dict.fromkeys(tokens))[:16]
    token_set = set(tokens)
    issue_types = {item.value for item in IssueType}
    normalized_hints = [AGGREGATE_TYPES.get(value, value) for value in hints[:32]]
    normalized_hints = [
        {"DB": "DATABASE", "API": "API_CONTRACT"}.get(value, value) for value in normalized_hints
    ]
    issues = {value for value in normalized_hints if value in issue_types}
    issues.update(issue for issue, terms in _ISSUE_TERMS.items() if token_set.intersection(terms))
    return words, issues


def _query(project_id: int, target_type: TargetType | None, *, all_targets: bool = False):
    query = (
        select(ReviewMemorySource, ReviewMemoryEntry, ReviewMemoryProjectSource, ReviewItemFeedback)
        .join(ReviewMemoryEntry, ReviewMemoryEntry.source_id == ReviewMemorySource.id)
        .join(
            ReviewMemoryProjectSource, ReviewMemoryProjectSource.source_id == ReviewMemorySource.id
        )
        .outerjoin(
            ReviewItemFeedback, ReviewItemFeedback.id == ReviewMemorySource.source_feedback_id
        )
        .where(
            ReviewMemoryProjectSource.project_id == project_id,
            ReviewMemoryProjectSource.state == "ACTIVE",
            ReviewMemorySource.state == "PUBLISHED",
            ReviewMemorySource.deleted_at.is_(None),
            or_(ReviewMemorySource.project_id == project_id, and_(*shared_source_conditions())),
            ReviewMemoryEntry.state == "ACTIVE",
        )
        .options(undefer(ReviewMemoryEntry.content))
        .order_by(ReviewMemoryEntry.updated_at.desc(), ReviewMemoryEntry.id.desc())
    )
    if not all_targets:
        query = query.where(
            or_(
                ReviewMemoryEntry.target_type.is_(None),
                ReviewMemoryEntry.target_type == target_type,
            ),
            or_(
                ReviewMemoryProjectSource.target_type.is_(None),
                ReviewMemoryProjectSource.target_type == target_type,
            ),
        )
    return query


def _matching_paths(row, paths: list[str]) -> set[str]:
    _, entry, binding, _ = row
    binding_paths = _labels(binding.path_globs_json)
    entry_paths = _labels(entry.path_globs_json)
    return {
        path
        for path in paths
        if (not binding_paths or any(fnmatchcase(path, glob) for glob in binding_paths))
        and (not entry_paths or any(fnmatchcase(path, glob) for glob in entry_paths))
    }


def _applicable(row, paths: list[str], skips: Counter) -> bool:
    source, _, binding, feedback = row
    if not _matching_paths(row, paths):
        skips["PATH_SCOPE"] += 1
        return False
    if source.origin == "FEEDBACK" and not (
        feedback is not None
        and feedback.project_id == source.project_id
        and binding.project_id == source.project_id
        and source.visibility == "PROJECT"
        and feedback.source_type == "AI_FINDING"
        and feedback.feedback_type == "FALSE_POSITIVE"
        and feedback.status == "VALID"
        and source.feedback_digest == feedback_digest(feedback)
    ):
        skips["FEEDBACK_STALE"] += 1
        return False
    return True


def _entry(row) -> MemoryEntryDraft:
    _, entry, _, _ = row
    value = MemoryEntryDraft(
        heading=entry.heading,
        content=entry.content,
        target_type=entry.target_type,
        issue_type=entry.issue_type,
        path_globs=_labels(entry.path_globs_json),
        keywords=_labels(entry.keywords_json),
        load_mode=entry.load_mode,
    )
    validate_entry_for_publication(row[0].kind, value)
    return value


def _core_item(row) -> CoreBudgetItem:
    source, entry, binding, _ = row
    return CoreBudgetItem(
        **{**_entry(row).model_dump(), "target_type": binding.target_type or entry.target_type},
        source_id=source.id,
        entry_id=entry.id,
        source_version=source.version,
        entry_version=entry.version,
        source_kind=source.kind,
        source_title=source.title,
        binding_path_globs=_labels(binding.path_globs_json),
    )


def _rank(row, words: list[str], issues: set[str]) -> tuple:
    source, entry, binding, _ = row
    paths = _labels(entry.path_globs_json) + _labels(binding.path_globs_json)
    specificity = max((len(re.sub(r"[?*\[\]]", "", path)) for path in paths), default=0)
    explicit = " ".join([source.title, entry.heading, *_labels(entry.keywords_json)]).casefold()
    # Boolean hits: repeated words in an entry cannot boost its score without bound.
    return (
        int(entry.target_type is not None or binding.target_type is not None),
        specificity,
        int(entry.issue_type in issues),
        int(any(word in explicit for word in words)),
        int(any(word in entry.content.casefold() for word in words)),
        entry.updated_at,
        entry.id,
    )


def _candidates(db, query, paths, words, issues, skips):
    keyword_conditions = [
        column.contains(word, autoescape=True)
        for word in words
        for column in (
            ReviewMemorySource.title,
            ReviewMemoryEntry.heading,
            ReviewMemoryEntry.keywords_json,
            ReviewMemoryEntry.content,
        )
    ]
    groups = [
        (ReviewMemoryEntry.issue_type.in_(issues), 80),
        (or_(*keyword_conditions) if keyword_conditions else ReviewMemoryEntry.id < 0, 80),
        (
            or_(ReviewMemoryEntry.issue_type.is_(None), ReviewMemoryEntry.issue_type == "GENERAL")
            if issues
            else ReviewMemoryEntry.id > 0,
            40,
        ),
    ]
    candidates = {}
    limited = False
    for condition, quota in groups:
        rows = list(
            db.execute(
                query.where(ReviewMemoryEntry.load_mode == "ON_DEMAND", condition).limit(300)
            ).all()
        )
        limited = limited or len(rows) == 300
        applicable = []
        for row in rows:
            if _applicable(row, paths, skips):
                try:
                    _entry(row)
                except (AppError, ValueError):
                    skips["INVALID_ENTRY"] += 1
                    continue
                applicable.append(row)
        applicable.sort(key=lambda row: _rank(row, words, issues), reverse=True)
        for row in applicable[:quota]:
            candidates[row[1].id] = row
    return sorted(
        candidates.values(), key=lambda row: _rank(row, words, issues), reverse=True
    ), limited


def _legacy_digests(policy_context: dict) -> tuple[set[int], set[str], set[int]]:
    feedback_ids, hashes, truncated_feedback_ids = set(), set(), set()
    # Only items whose full rendered text actually reached reviewInstructions can suppress memory.
    for item in policy_context.get("items") or []:
        feedback_id = item.get("sourceFeedbackId")
        if item.get("contentTruncated", True):
            if feedback_id:
                truncated_feedback_ids.add(feedback_id)
            continue
        hashes.add(normalized_hash(str(item.get("content") or "")))
        if feedback_id:
            feedback_ids.add(feedback_id)
    return feedback_ids, hashes, truncated_feedback_ids


def _on_demand_context(rows) -> str:
    if not rows:
        return ""
    payload = []
    for row in rows:
        source, entry, binding, _ = row
        payload.append(
            {
                **_entry(row).model_dump(mode="json", by_alias=True),
                "sourceId": source.id,
                "entryId": entry.id,
                "sourceVersion": source.version,
                "entryVersion": entry.version,
                "sourceTitle": source.title,
                "kind": source.kind,
                "bindingId": binding.id,
                "bindingVersion": binding.version,
                "bindingTargetType": binding.target_type,
                "bindingPaths": _labels(binding.path_globs_json),
            }
        )
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    body = body.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return (
        "\n<project_review_memory>\n按需审查步骤与历史案例（作为背景，仍需本次代码证据）：\n"
        + body
        + "\n</project_review_memory>"
    )


def _summary(row, issues, words) -> MemorySelectedSummary:
    source, entry, binding, _ = row
    paths = _labels(binding.path_globs_json) + _labels(entry.path_globs_json)
    applicability = f"关联端={binding.target_type or '*'}；章节端={entry.target_type or '*'}；问题={entry.issue_type or '*'}"
    reasons = ["CORE_REQUIRED"] if entry.load_mode == "CORE" else ["ON_DEMAND"]
    if entry.issue_type in issues:
        reasons.append("ISSUE_MATCH")
    if paths:
        reasons.append("PATH_MATCH")
    if words and _rank(row, words, issues)[3]:
        reasons.append("KEYWORD_MATCH")
    return MemorySelectedSummary(
        source_id=source.id,
        entry_id=entry.id,
        binding_id=binding.id,
        owner_project_id=source.project_id,
        source_version=source.version,
        entry_version=entry.version,
        binding_version=binding.version,
        kind=source.kind,
        load_mode=entry.load_mode,
        content_hash=normalized_hash(entry.content),
        title=_short(source.title),
        heading=_short(entry.heading),
        applicability=_short(applicability),
        selection_reason=reasons,
        path_sample=_short(paths[0]) if paths else None,
        path_count=len(paths),
    )


def _select(db, project_id, target_type, paths, diff, issue_hints, policy_context):
    settings = read_settings(db, project_id)
    snapshot = MemorySnapshot(
        policy_version=settings.version,
        project_id=project_id,
        target_type=target_type,
        lookup_status="DISABLED",
        disabled_reason="SCHEMA_PENDING" if not settings.schema_ready else "PROJECT_DISABLED",
    )
    if not settings.enabled:
        return MemorySelection("", snapshot)
    snapshot.disabled_reason = None
    query = _query(project_id, target_type)
    # No LIKE/topK limit on CORE. Invalid required data must fail before any job is persisted.
    core_rows = list(db.execute(query.where(ReviewMemoryEntry.load_mode == "CORE")).all())
    skips = Counter()
    core_rows = [row for row in core_rows if _applicable(row, paths, skips)]
    for row in core_rows:
        _core_item(row)
    # Validate pre-dedup count/budget too; old policy overlap cannot hide invalid CORE config.
    core_text = render_core_context([_core_item(row) for row in core_rows])
    if len(core_rows) > 20 or len(core_text.encode("utf-8")) > 8000:
        raise AppError("MEMORY_CORE_BUDGET_EXCEEDED", "Required memory exceeds its budget", 409)
    words, issues = _hints(paths, diff, issue_hints)
    snapshot.issue_hints_unknown = not bool(issues)
    legacy_ids, legacy_hashes, truncated_ids = _legacy_digests(policy_context)
    covered_paths: dict[str, set[str]] = {}
    selected_core, selected_demand = [], []

    def duplicate(row):
        source, entry, _, _ = row
        digest = normalized_hash(entry.content)
        if source.source_feedback_id in legacy_ids or digest in legacy_hashes:
            skips["LEGACY_POLICY_LOADED"] += 1
            return True
        if digest in covered_paths and _matching_paths(row, paths).issubset(covered_paths[digest]):
            skips["DUPLICATE_CONTENT"] += 1
            return True
        if source.source_feedback_id in truncated_ids:
            skips["LEGACY_TRUNCATED_OVERLAP"] += 1
        return False

    core_rows.sort(key=lambda row: _rank(row, words, issues), reverse=True)
    for row in core_rows:
        if not duplicate(row):
            selected_core.append(row)
            covered_paths.setdefault(normalized_hash(row[1].content), set()).update(
                _matching_paths(row, paths)
            )
    core_text = render_core_context([_core_item(row) for row in selected_core])
    partial = False
    try:
        has_entries = db.scalar(
            select(
                exists(
                    _query(project_id, target_type, all_targets=True)
                    .order_by(None)
                    .with_only_columns(ReviewMemoryEntry.id)
                )
            )
        )
        demand_rows, limited = _candidates(db, query, paths, words, issues, skips)
        snapshot.candidate_scan_limited = limited
    except SQLAlchemyError:
        # CORE text/metadata are already in memory from the same read view. No variable reread.
        partial = True
        has_entries, demand_rows = True, []
        _LOGGER.warning("Memory optional lookup failed projectId=%s", project_id)
        skips["OPTIONAL_LOOKUP_FAILED"] += 1
    for row in demand_rows:
        if duplicate(row):
            continue
        if len(selected_demand) >= 8:
            skips["ON_DEMAND_COUNT_BUDGET"] += 1
            continue
        candidate_text = _on_demand_context([*selected_demand, row])
        if len(candidate_text.encode("utf-8")) > 6000:
            skips["ON_DEMAND_BYTE_BUDGET"] += 1
            continue
        selected_demand.append(row)
        covered_paths.setdefault(normalized_hash(row[1].content), set()).update(
            _matching_paths(row, paths)
        )
    text = core_text + _on_demand_context(selected_demand)
    selected = [*selected_core, *selected_demand]
    snapshot.lookup_status = (
        "PARTIAL_LOOKUP"
        if partial
        else "LOADED"
        if selected
        else "NO_MATCH"
        if has_entries or skips
        else "EMPTY"
    )
    snapshot.injected_bytes = len(text.encode("utf-8"))
    snapshot.skip_reasons = dict(skips)
    snapshot.selected = [_summary(row, issues, words) for row in selected]
    if len(snapshot.model_dump_json(by_alias=True).encode("utf-8")) > 32768:
        raise AppError("MEMORY_SNAPSHOT_INVALID", "Memory metadata exceeds its budget", 500)
    return MemorySelection(text, snapshot)


def select_review_memories(
    db: Session,
    *,
    project_id: int,
    target_type: TargetType | None,
    changed_files: list[str],
    diff_text: str = "",
    issue_hints: list[str] | None = None,
    policy_context: dict | None = None,
) -> MemorySelection:
    bind = db.get_bind()
    if bind.dialect.name in {"mysql", "mariadb"}:
        bind = bind.execution_options(isolation_level="REPEATABLE READ")
    try:
        with Session(bind=bind, autoflush=False) as reader:
            return _select(
                reader,
                project_id,
                target_type,
                changed_files,
                diff_text,
                issue_hints or [],
                policy_context or {},
            )
    except AppError as exception:
        if exception.code in BLOCKING_MEMORY_CODES:
            raise
        raise AppError(
            "MEMORY_LOOKUP_FAILED", "Required memory could not be validated", 503
        ) from None
    except (SQLAlchemyError, ValueError, TypeError):
        raise AppError("MEMORY_LOOKUP_FAILED", "Required memory could not be read", 503) from None
