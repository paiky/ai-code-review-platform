import hashlib
import json
import re
from typing import get_args
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.json_utils import utc_now
from app.project_integration.schemas import TargetType
from app.review_memory import repository
from app.review_memory.models import ReviewMemoryEntry, ReviewMemorySource
from app.review_memory.parsing import PARSER_VERSION, ParsedMemory
from app.review_memory.schemas import (
    MAX_CORE_BYTES,
    MAX_CORE_ENTRIES,
    MAX_ENTRY_CONTENT_BYTES,
    CoreBudgetItem,
    EntryState,
    LoadMode,
    MemoryEntryDraft,
    MemoryEntryResponse,
    MemoryEntryCreate,
    MemoryEntryUpdate,
    MemoryKind,
    MemoryOrigin,
    MemorySourceDetail,
    MemorySourceDraft,
    MemorySourcePage,
    MemorySourceQuery,
    MemorySourceSummary,
    MemorySourceUpdate,
    MemoryPublish,
    MemoryUploadMetadata,
    MemoryWritebackSummary,
    SourceState,
)


def require_project(db: Session, project_id: int) -> None:
    if repository.get_project(db, project_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", "Project not found", 404)


def require_source(
    db: Session,
    project_id: int,
    source_id: int,
    *,
    expected_version: int | None = None,
    lock: bool = False,
) -> ReviewMemorySource:
    record = repository.get_source(db, project_id, source_id, lock=lock)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", "Memory source not found in project", 404)
    if expected_version is not None:
        assert_version(record.version, expected_version)
    return record


def assert_version(actual: int, expected: int) -> None:
    if type(expected) is not int or expected < 1 or actual != expected:
        raise AppError(
            "MEMORY_VERSION_CONFLICT", "Memory version changed; reload before editing", 409
        )


def validate_source_transition(current: SourceState, requested: SourceState) -> None:
    allowed = {
        SourceState.DRAFT: {SourceState.PUBLISHED, SourceState.DELETED},
        SourceState.PUBLISHED: {SourceState.DISABLED, SourceState.DELETED},
        SourceState.DISABLED: {SourceState.PUBLISHED, SourceState.DELETED},
        SourceState.DELETED: set(),
    }
    if requested not in allowed.get(current, set()):
        raise AppError(
            "MEMORY_STATE_CONFLICT", "Memory source state does not allow this transition", 409
        )


def validate_entry_for_publication(kind: MemoryKind, entry: MemoryEntryDraft) -> None:
    if entry.load_mode == LoadMode.CORE and kind not in {
        MemoryKind.STANDARD,
        MemoryKind.ARCHITECTURE,
    }:
        raise AppError(
            "MEMORY_CORE_KIND_INVALID", "Only standards and architecture can be CORE", 409
        )
    if len(entry.content.encode("utf-8")) > MAX_ENTRY_CONTENT_BYTES:
        raise AppError(
            "MEMORY_ENTRY_TOO_LARGE", "Split this entry before publishing (4000 bytes)", 409
        )
    if kind in {MemoryKind.PITFALL, MemoryKind.INCIDENT}:
        labels = ("适用条件", "原误判及原因", "正确判断方法", "下次应查证据", "例外/失效条件")
        pattern = r"^\s*(?:#{1,6}\s+)?(" + "|".join(map(re.escape, labels)) + r")[：:]?\s*"
        matches = list(re.finditer(pattern, entry.content, re.MULTILINE))
        if [match.group(1) for match in matches] != list(labels) or any(
            not entry.content[
                match.end() : matches[i + 1].start() if i + 1 < len(matches) else None
            ].strip()
            for i, match in enumerate(matches)
        ):
            raise AppError(
                "MEMORY_CASE_TEMPLATE_REQUIRED",
                "Case requires five non-empty template sections",
                409,
            )


def _entry_validation_errors(kind: MemoryKind, entry: MemoryEntryDraft) -> list[str]:
    try:
        validate_entry_for_publication(kind, entry)
    except AppError as exception:
        return [exception.code]
    return []


def create_manual_draft(
    db: Session,
    project_id: int,
    draft: MemorySourceDraft,
) -> MemorySourceDetail:
    """Flush a draft in the caller's transaction; never publish or commit it here."""
    if repository.get_project(db, project_id, lock=True) is None:
        raise AppError("RESOURCE_NOT_FOUND", "Project not found", 404)
    # Revalidate at the service boundary, including models constructed without validation.
    draft = MemorySourceDraft.model_validate(draft.model_dump())
    source = ReviewMemorySource(
        project_id=project_id,
        kind=draft.kind,
        origin=MemoryOrigin.MANUAL,
        title=draft.title,
        description=draft.description,
        state=SourceState.DRAFT,
        version=1,
    )
    db.add(source)
    db.flush()
    for ordinal, entry in enumerate(draft.entries):
        record = ReviewMemoryEntry(
            source_id=source.id,
            section_key=uuid4().hex,
            heading=entry.heading,
            ordinal=ordinal,
            content=entry.content,
            target_type=entry.target_type,
            issue_type=entry.issue_type,
            path_globs_json=json.dumps(entry.path_globs, ensure_ascii=False),
            keywords_json=json.dumps(entry.keywords, ensure_ascii=False),
            load_mode=entry.load_mode,
            state=EntryState.DRAFT,
            version=1,
            content_sha256=hashlib.sha256(entry.content.encode("utf-8")).hexdigest(),
            validation_errors_json=json.dumps(_entry_validation_errors(draft.kind, entry)),
        )
        db.add(record)
    db.flush()
    return get_project_source(db, project_id, source.id)


def list_project_sources(
    db: Session,
    project_id: int,
    query: MemorySourceQuery,
) -> MemorySourcePage:
    require_project(db, project_id)
    query = MemorySourceQuery.model_validate(query.model_dump())
    records, total = repository.list_sources(db, project_id, query)
    return MemorySourcePage(
        items=[_source_summary(record) for record in records],
        total=total,
        page_no=query.page_no,
        page_size=query.page_size,
    )


def get_project_source(db: Session, project_id: int, source_id: int) -> MemorySourceDetail:
    source = require_source(db, project_id, source_id)
    entries = repository.list_entries(db, project_id, source_id)
    return MemorySourceDetail(
        **_source_summary(source).model_dump(),
        entries=[_entry_response(entry) for entry in entries],
        original_filename=source.original_filename,
        media_type=source.media_type,
        parser_version=source.parser_version,
        parse_warnings=_string_list(source.parse_warnings_json),
        has_original=source.original_sha256 is not None,
        confirmed_by=source.confirmed_by,
        confirmed_at=source.confirmed_at,
        legacy_policy_ids=repository.legacy_policy_ids(db, project_id, source.source_feedback_id),
    )


def get_project_entry(
    db: Session,
    project_id: int,
    source_id: int,
    entry_id: int,
) -> MemoryEntryResponse:
    record = repository.get_entry(db, project_id, source_id, entry_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", "Memory entry not found in project source", 404)
    return _entry_response(record)


def get_project_writeback(
    db: Session, project_id: int, writeback_id: int
) -> MemoryWritebackSummary:
    record = repository.get_writeback(db, project_id, writeback_id)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", "Memory writeback not found in project", 404)
    return MemoryWritebackSummary(
        id=record.id,
        feedback_id=record.feedback_id,
        source_id=record.source_id,
        state=record.state,
        attempts=record.attempts,
        last_error_code=record.last_error_code,
    )


def get_project_core_items(
    db: Session, project_id: int, *, lock: bool = False
) -> list[CoreBudgetItem]:
    require_project(db, project_id)
    return [
        CoreBudgetItem(
            **_entry_draft(entry).model_dump(),
            source_id=source.id,
            entry_id=entry.id,
            source_version=source.version,
            entry_version=entry.version,
            source_kind=source.kind,
            source_title=source.title,
        )
        for source, entry in repository.list_project_core_entries(db, project_id, lock=lock)
    ]


def _locked_source(
    db: Session, project_id: int, source_id: int, version: int
) -> ReviewMemorySource:
    if repository.get_project(db, project_id, lock=True) is None:
        raise AppError("RESOURCE_NOT_FOUND", "Project not found", 404)
    source = require_source(db, project_id, source_id, expected_version=version, lock=True)
    _require_manageable(source)
    return source


def _require_manageable(source: ReviewMemorySource) -> None:
    if source.state == SourceState.DELETED:
        raise AppError("MEMORY_STATE_CONFLICT", "Deleted memory cannot be modified", 409)
    if source.origin == MemoryOrigin.FEEDBACK:
        raise AppError(
            "MEMORY_FEEDBACK_CONFIRM_REQUIRED",
            "Feedback memories require dedicated confirmation",
            409,
        )


def _touch(source: ReviewMemorySource) -> None:
    source.version += 1
    source.updated_at = utc_now()


def _finish_mutation(db: Session, source: ReviewMemorySource) -> MemorySourceDetail:
    db.flush()
    validate_core_budget(get_project_core_items(db, source.project_id, lock=True))
    return get_project_source(db, source.project_id, source.id)


def _validate_source_entries(source: ReviewMemorySource, entries: list[MemoryEntryDraft]) -> None:
    try:
        MemorySourceDraft(
            kind=source.kind, title=source.title, description=source.description, entries=entries
        )
    except ValidationError as exception:
        raise AppError(
            "MEMORY_SOURCE_INVALID", "Source entries exceed count/size or have invalid labels", 400
        ) from exception


def _apply_entry(record: ReviewMemoryEntry, kind: MemoryKind, draft: MemoryEntryDraft) -> None:
    for field in ("heading", "content", "target_type", "issue_type", "load_mode"):
        setattr(record, field, getattr(draft, field))
    record.path_globs_json = json.dumps(draft.path_globs, ensure_ascii=False)
    record.keywords_json = json.dumps(draft.keywords, ensure_ascii=False)
    record.content_sha256 = hashlib.sha256(draft.content.encode("utf-8")).hexdigest()
    record.validation_errors_json = json.dumps(_entry_validation_errors(kind, draft))


def create_upload_draft(
    db: Session,
    project_id: int,
    parsed: ParsedMemory,
    original: bytes,
    metadata: MemoryUploadMetadata,
) -> MemorySourceDetail:
    if repository.get_project(db, project_id, lock=True) is None:
        raise AppError("RESOURCE_NOT_FOUND", "Project not found", 404)
    if metadata.replacement_of_id is not None:
        old = require_source(
            db,
            project_id,
            metadata.replacement_of_id,
            expected_version=metadata.expected_replaced_version,
            lock=True,
        )
        _require_manageable(old)
        if old.kind != metadata.kind:
            raise AppError("MEMORY_REPLACEMENT_INVALID", "Replacement requires the same kind", 409)
    digest = hashlib.sha256(original).hexdigest()
    warnings = list(parsed.warnings)
    if repository.has_duplicate_upload(db, project_id, digest):
        warnings.append("本项目已有相同原件；本次仍保存为独立草稿。")
    detail = create_manual_draft(db, project_id, parsed.draft)
    source = require_source(db, project_id, detail.id)
    source.origin = MemoryOrigin.UPLOAD
    source.original_filename = parsed.filename
    source.media_type = parsed.media_type
    source.original_bytes = original
    source.original_sha256 = digest
    source.extracted_text = parsed.text
    source.parser_version = PARSER_VERSION
    source.parse_warnings_json = json.dumps(warnings, ensure_ascii=False)
    source.replacement_of_id = metadata.replacement_of_id
    db.flush()
    return get_project_source(db, project_id, source.id)


def update_source(
    db: Session, project_id: int, source_id: int, request: MemorySourceUpdate
) -> MemorySourceDetail:
    source = _locked_source(db, project_id, source_id, request.expected_version)
    source.title, source.description = request.title, request.description
    _touch(source)
    return _finish_mutation(db, source)


def add_entry(
    db: Session, project_id: int, source_id: int, request: MemoryEntryCreate
) -> MemorySourceDetail:
    source = _locked_source(db, project_id, source_id, request.expected_source_version)
    records = repository.list_entries(db, project_id, source_id, lock=True)
    _validate_source_entries(source, [*map(_entry_draft, records), request.entry])
    record = ReviewMemoryEntry(
        source_id=source.id,
        section_key=uuid4().hex,
        ordinal=max((row.ordinal for row in records), default=-1) + 1,
        state=EntryState.DRAFT,
        version=1,
    )
    _apply_entry(record, source.kind, request.entry)
    db.add(record)
    _touch(source)
    return _finish_mutation(db, source)


def update_entry(
    db: Session, project_id: int, source_id: int, entry_id: int, request: MemoryEntryUpdate
) -> MemorySourceDetail:
    source = _locked_source(db, project_id, source_id, request.expected_source_version)
    records = repository.list_entries(db, project_id, source_id, lock=True)
    record = next((row for row in records if row.id == entry_id), None)
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", "Memory entry not found in project source", 404)
    assert_version(record.version, request.expected_version)
    if request.entry is not None:
        _validate_source_entries(
            source, [request.entry if row.id == entry_id else _entry_draft(row) for row in records]
        )
        _apply_entry(record, source.kind, request.entry)
        record.state = EntryState.DRAFT
    else:
        record.state = EntryState.DISABLED
    record.version += 1
    record.updated_at = utc_now()
    _touch(source)
    return _finish_mutation(db, source)


def publish_source(
    db: Session, project_id: int, source_id: int, request: MemoryPublish
) -> MemorySourceDetail:
    source = _locked_source(db, project_id, source_id, request.expected_version)
    records = repository.list_entries(db, project_id, source_id, lock=True)
    by_id = {row.id: row for row in records}
    selected = {item.id for item in request.selected_entries}
    for item in request.selected_entries:
        record = by_id.get(item.id)
        if record is None:
            raise AppError("RESOURCE_NOT_FOUND", f"Memory entry {item.id} not found in source", 404)
        assert_version(record.version, item.expected_version)
        try:
            validate_entry_for_publication(source.kind, _entry_draft(record))
        except AppError as exception:
            raise AppError(
                exception.code, f"Entry {record.id}: {exception.message}", exception.status_code
            ) from exception
    _validate_source_entries(source, [_entry_draft(row) for row in records])
    if source.replacement_of_id is not None and source.confirmed_at is None:
        if request.expected_replaced_version is None:
            raise AppError(
                "MEMORY_REPLACEMENT_VERSION_REQUIRED", "expectedReplacedVersion is required", 409
            )
        old = require_source(
            db,
            project_id,
            source.replacement_of_id,
            expected_version=request.expected_replaced_version,
            lock=True,
        )
        _require_manageable(old)
        if old.kind != source.kind or old.id == source.id:
            raise AppError("MEMORY_REPLACEMENT_INVALID", "Invalid replacement source", 409)
        old.state = SourceState.DISABLED
        _touch(old)
    elif request.expected_replaced_version is not None:
        raise AppError("MEMORY_REPLACEMENT_INVALID", "No pending replacement on this source", 409)
    if source.state != SourceState.PUBLISHED:
        validate_source_transition(SourceState(source.state), SourceState.PUBLISHED)
    for record in records:
        if record.id in selected:
            record.state = EntryState.ACTIVE
            record.validation_errors_json = "[]"
        elif source.state == SourceState.DISABLED and record.state == EntryState.ACTIVE:
            record.state = EntryState.DISABLED
        else:
            continue
        record.version += 1
        record.updated_at = utc_now()
    source.state = SourceState.PUBLISHED
    operator = (request.operator_name or "").strip()
    source.confirmed_by = (
        f"填报（未经身份验证）：{operator}" if operator else "未提供身份（未经验证）"
    )
    source.confirmed_at = utc_now()
    _touch(source)
    return _finish_mutation(db, source)


def change_source_state(
    db: Session, project_id: int, source_id: int, expected_version: int, state: SourceState
) -> MemorySourceDetail:
    source = _locked_source(db, project_id, source_id, expected_version)
    validate_source_transition(SourceState(source.state), state)
    if state not in {SourceState.DISABLED, SourceState.DELETED}:
        raise AppError("MEMORY_STATE_CONFLICT", "Use publish to activate memory", 409)
    source.state = state
    if state == SourceState.DELETED:
        source.deleted_at = utc_now()
    _touch(source)
    return _finish_mutation(db, source)


def get_original(db: Session, project_id: int, source_id: int) -> tuple[str, bytes]:
    source = require_source(db, project_id, source_id)
    if source.original_filename is None or source.original_bytes is None:
        raise AppError("RESOURCE_NOT_FOUND", "Memory source has no original file", 404)
    return source.original_filename, source.original_bytes


def render_core_context(items: list[CoreBudgetItem]) -> str:
    if not items:
        return ""
    payload = [item.model_dump(mode="json", by_alias=True) for item in items]
    # Escape delimiters as text, not commands. M6 must reuse this exact rendering for this budget.
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    body = body.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return (
        "<project_review_memory>\n核心规范（仍需本次代码证据）：\n"
        + body
        + "\n</project_review_memory>"
    )


def validate_core_budget(items: list[CoreBudgetItem]) -> dict[str, int]:
    """Validate all projected CORE entries, without relying on path scopes being disjoint."""
    validated = [CoreBudgetItem.model_validate(item.model_dump()) for item in items]
    seen = set()
    for item in validated:
        validate_entry_for_publication(item.source_kind, item)
        if item.load_mode != LoadMode.CORE or (item.source_id, item.entry_id) in seen:
            raise AppError("MEMORY_CORE_INVALID", "CORE budget requires unique CORE entries", 409)
        seen.add((item.source_id, item.entry_id))
    sizes = {}
    for target in get_args(TargetType):
        applicable = [item for item in validated if item.target_type in (None, target)]
        size = len(render_core_context(applicable).encode("utf-8"))
        if len(applicable) > MAX_CORE_ENTRIES or size > MAX_CORE_BYTES:
            raise AppError(
                "MEMORY_CORE_BUDGET_EXCEEDED",
                f"CORE budget exceeds 20 entries or 8000 bytes for {target}",
                409,
            )
        sizes[target] = size
    return sizes


def _source_summary(record: ReviewMemorySource) -> MemorySourceSummary:
    return MemorySourceSummary(
        id=record.id,
        project_id=record.project_id,
        kind=record.kind,
        origin=record.origin,
        title=record.title,
        description=record.description,
        state=record.state,
        version=record.version,
        source_feedback_id=record.source_feedback_id,
        replacement_of_id=record.replacement_of_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _string_list(raw_value: str | None) -> list[str]:
    try:
        value = json.loads(raw_value) if raw_value is not None else []
    except (ValueError, TypeError) as exception:
        raise AppError("MEMORY_DATA_INVALID", "Memory metadata is invalid", 409) from exception
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AppError("MEMORY_DATA_INVALID", "Memory metadata must be a string list", 409)
    return value


def _entry_draft(record: ReviewMemoryEntry) -> MemoryEntryDraft:
    try:
        return MemoryEntryDraft(
            heading=record.heading,
            content=record.content,
            target_type=record.target_type,
            issue_type=record.issue_type,
            path_globs=_string_list(record.path_globs_json),
            keywords=_string_list(record.keywords_json),
            load_mode=record.load_mode,
        )
    except ValidationError as exception:
        raise AppError("MEMORY_DATA_INVALID", "Stored memory entry is invalid", 409) from exception


def _entry_response(record: ReviewMemoryEntry) -> MemoryEntryResponse:
    return MemoryEntryResponse(
        **_entry_draft(record).model_dump(),
        id=record.id,
        source_id=record.source_id,
        section_key=record.section_key,
        ordinal=record.ordinal,
        state=record.state,
        version=record.version,
        content_sha256=record.content_sha256,
        validation_errors=_string_list(record.validation_errors_json),
    )
