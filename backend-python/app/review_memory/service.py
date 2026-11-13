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
from app.review_memory.models import (
    ReviewMemoryEntry,
    ReviewMemoryProjectSource,
    ReviewMemorySource,
)
from app.review_memory.parsing import ParsedMemory
from app.review_memory.schemas import (
    MAX_CORE_BYTES,
    MAX_CORE_ENTRIES,
    MAX_ENTRY_CONTENT_BYTES,
    BindingState,
    CoreBudgetItem,
    EntryState,
    LoadMode,
    MemoryBindingResult,
    MemoryBindingSummary,
    MemoryBindingUpdate,
    MemoryEntryDraft,
    MemoryEntryResponse,
    MemoryEntryCreate,
    MemoryEntryUpdate,
    MemoryKind,
    MemoryOrigin,
    MemorySourceDetail,
    MemorySourceImpact,
    MemorySourceDraft,
    MemorySourcePage,
    MemorySourceQuery,
    MemorySourceSummary,
    MemorySourceUpdate,
    MemorySharedQuery,
    MemoryPublish,
    MemoryUploadMetadata,
    MemoryWritebackSummary,
    SourceState,
    SourceVisibility,
)


def select_review_memories(db: Session, **kwargs):
    from app.review_memory.retrieval import select_review_memories as select_memories

    return select_memories(db, **kwargs)


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
        visibility=SourceVisibility.PROJECT,
        kind=draft.kind,
        origin=MemoryOrigin.MANUAL,
        title=draft.title,
        description=draft.description,
        state=SourceState.DRAFT,
        version=1,
    )
    db.add(source)
    db.flush()
    db.add(
        ReviewMemoryProjectSource(
            project_id=project_id,
            source_id=source.id,
            state=BindingState.ACTIVE,
            version=1,
        )
    )
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
    bindings = repository.project_bindings_by_source(db, project_id, [row.id for row in records])
    return MemorySourcePage(
        items=[
            _source_summary(record, bindings.get(record.id), record.project_id == project_id)
            for record in records
        ],
        total=total,
        page_no=query.page_no,
        page_size=query.page_size,
    )


def get_project_source(db: Session, project_id: int, source_id: int) -> MemorySourceDetail:
    source = _readable_source(db, project_id, source_id)
    return _source_detail(db, source, project_id)


def _is_shared(source: ReviewMemorySource) -> bool:
    return (
        source.visibility == SourceVisibility.SHARED
        and source.state == SourceState.PUBLISHED
        and source.deleted_at is None
        and source.kind in {MemoryKind.STANDARD, MemoryKind.ARCHITECTURE, MemoryKind.SKILL}
        and source.origin != MemoryOrigin.FEEDBACK
        and (source.replacement_of_id is None or source.confirmed_at is not None)
    )


def _readable_source(db: Session, project_id: int | None, source_id: int) -> ReviewMemorySource:
    source = repository.get_source(db, None, source_id)
    if source is not None:
        if project_id is not None and project_id == source.project_id:
            return source
        binding = (
            repository.get_project_source_binding(db, project_id, source_id)
            if project_id is not None
            else None
        )
        if _is_shared(source) and (
            project_id is None or binding is not None and binding.state == BindingState.ACTIVE
        ):
            return source
    raise AppError("RESOURCE_NOT_FOUND", "Memory source not found", 404)


def _source_detail(
    db: Session, source: ReviewMemorySource, project_id: int | None, *, management: bool = False
) -> MemorySourceDetail:
    owner = management or project_id is not None and project_id == source.project_id
    binding = (
        repository.get_project_source_binding(db, project_id, source.id)
        if project_id is not None
        else None
    )
    entries = repository.list_entries(db, source.project_id, source.id)
    return MemorySourceDetail(
        **_source_summary(source, binding, owner).model_dump(),
        entries=[
            _entry_response(entry) for entry in entries if owner or entry.state == EntryState.ACTIVE
        ],
        original_filename=source.original_filename,
        media_type=source.media_type,
        parser_version=source.parser_version,
        parse_warnings=_string_list(source.parse_warnings_json),
        has_original=source.original_sha256 is not None,
        can_download_original=source.original_sha256 is not None
        and (owner or all(entry.state == EntryState.ACTIVE for entry in entries)),
        confirmed_by=source.confirmed_by,
        confirmed_at=source.confirmed_at,
        legacy_policy_ids=repository.legacy_policy_ids(
            db, source.project_id, source.source_feedback_id
        )
        if owner
        else [],
    )


def list_shared_sources(db: Session, query: MemorySharedQuery) -> MemorySourcePage:
    query = MemorySharedQuery.model_validate(query.model_dump())
    records, total = repository.list_sources(db, None, MemorySourceQuery(**query.model_dump()))
    return MemorySourcePage(
        items=[_source_summary(row) for row in records],
        total=total,
        page_no=query.page_no,
        page_size=query.page_size,
    )


def get_shared_source(db: Session, source_id: int) -> MemorySourceDetail:
    return _source_detail(db, _readable_source(db, None, source_id), None)


def get_source_impact(db: Session, project_id: int, source_id: int) -> MemorySourceImpact:
    source = require_source(db, project_id, source_id)
    bindings = repository.list_source_bindings(db, source_id)
    return MemorySourceImpact(
        source_id=source.id,
        source_version=source.version,
        project_ids=_active_project_ids(bindings),
        bindings=[_binding_summary(row) for row in bindings],
    )


def get_source_binding(db: Session, project_id: int, source_id: int) -> MemoryBindingResult:
    require_project(db, project_id)
    binding = repository.get_project_source_binding(db, project_id, source_id)
    source = repository.get_source(db, None, source_id)
    if binding is None or source is None:
        raise AppError("RESOURCE_NOT_FOUND", "Memory project binding not found", 404)
    return MemoryBindingResult(source_version=source.version, binding=_binding_summary(binding))


def update_source_binding(
    db: Session,
    project_id: int,
    source_id: int,
    request: MemoryBindingUpdate,
) -> MemoryBindingResult:
    request = MemoryBindingUpdate.model_validate(request.model_dump())
    source, bindings = _lock_source_group(db, project_id, source_id, reference=True)[source_id]
    binding = next((row for row in bindings if row.project_id == project_id), None)
    owner = source.project_id == project_id
    # Existing references may always be detached, even after the source was disabled.
    if (
        not owner
        and not _is_shared(source)
        and not (binding is not None and request.state == BindingState.DISABLED)
    ):
        raise AppError("RESOURCE_NOT_FOUND", "Shared memory source not found", 404)
    assert_version(source.version, request.expected_source_version)
    if binding is None:
        if request.expected_binding_version is not None or request.state != BindingState.ACTIVE:
            raise AppError("MEMORY_VERSION_CONFLICT", "Memory project binding does not exist", 409)
    elif request.expected_binding_version is None:
        raise AppError("MEMORY_VERSION_CONFLICT", "expectedBindingVersion is required", 409)
    else:
        assert_version(binding.version, request.expected_binding_version)
    if request.state == BindingState.ACTIVE:
        if source.state != SourceState.PUBLISHED or source.deleted_at is not None:
            raise AppError("MEMORY_STATE_CONFLICT", "Only published sources can be used", 409)
    if source.replacement_of_id is not None and source.confirmed_at is None:
        raise AppError(
            "MEMORY_REPLACEMENT_INVALID",
            "Replacement bindings are inherited at first publication",
            409,
        )
    old_paths = _string_list(binding.path_globs_json) if binding is not None else []
    reducing = request.state == BindingState.DISABLED or (
        binding is not None
        and binding.state == BindingState.ACTIVE
        and (binding.target_type is None or binding.target_type == request.target_type)
        and (
            not old_paths
            or bool(request.path_globs)
            and set(request.path_globs).issubset(old_paths)
        )
        and (
            binding.target_type != request.target_type or set(old_paths) != set(request.path_globs)
        )
    )
    if binding is None:
        binding = ReviewMemoryProjectSource(project_id=project_id, source_id=source_id, version=1)
        db.add(binding)
    else:
        binding.version += 1
    binding.state = request.state
    binding.target_type = request.target_type
    binding.path_globs_json = json.dumps(request.path_globs, ensure_ascii=False)
    binding.updated_at = utc_now()
    _touch(source)
    db.flush()
    if not reducing:
        _validate_project_budgets(
            db, _active_project_ids(repository.list_source_bindings(db, source.id, lock=True))
        )
    return MemoryBindingResult(source_version=source.version, binding=_binding_summary(binding))


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
            **{
                **_entry_draft(entry).model_dump(),
                "target_type": binding.target_type or entry.target_type,
            },
            source_id=source.id,
            entry_id=entry.id,
            source_version=source.version,
            entry_version=entry.version,
            source_kind=source.kind,
            source_title=source.title,
            binding_path_globs=_string_list(binding.path_globs_json),
        )
        for source, entry, binding in repository.list_project_core_entries(
            db, project_id, lock=lock
        )
    ]


def _active_project_ids(bindings: list[ReviewMemoryProjectSource]) -> list[int]:
    return sorted(row.project_id for row in bindings if row.state == BindingState.ACTIVE)


def _lock_source_group(
    db: Session,
    project_id: int,
    source_id: int,
    *,
    reference: bool = False,
    replacement: bool = False,
) -> dict[int, tuple[ReviewMemorySource, list[ReviewMemoryProjectSource]]]:
    # Use a separate read transaction; the writer only uses current reads after project locks.
    with Session(bind=db.get_bind(), autoflush=False) as lookup:
        primary = repository.get_source(lookup, None, source_id)
        if primary is None or not reference and primary.project_id != project_id:
            raise AppError("RESOURCE_NOT_FOUND", "Memory source not found in project", 404)
        source_ids = {source_id}
        if replacement and primary.replacement_of_id is not None and primary.confirmed_at is None:
            source_ids.add(primary.replacement_of_id)
        versions = {}
        project_ids = {project_id}
        for item_id in sorted(source_ids):
            item = repository.get_source(lookup, None, item_id)
            if item is None or item.project_id != primary.project_id:
                raise AppError("RESOURCE_NOT_FOUND", "Replacement source not found in project", 404)
            versions[item_id] = item.version
            project_ids.add(item.project_id)
            project_ids.update(
                row.project_id for row in repository.list_source_bindings(lookup, item_id)
            )
    for item_id in sorted(project_ids):
        if repository.get_project(db, item_id, lock=True) is None:
            raise AppError("RESOURCE_NOT_FOUND", "Project not found", 404)
    sources = {}
    for item_id in sorted(source_ids):
        item = repository.get_source(db, None, item_id, lock=True)
        if item is None or item.version != versions[item_id]:
            raise AppError("MEMORY_VERSION_CONFLICT", "Memory changed during lock acquisition", 409)
        sources[item_id] = item
    result = {}
    current_projects = {project_id}
    for item_id, item in sources.items():
        bindings = repository.list_source_bindings(db, item_id, lock=True)
        current_projects.add(item.project_id)
        current_projects.update(row.project_id for row in bindings)
        result[item_id] = (item, bindings)
    if current_projects != project_ids:
        raise AppError("MEMORY_VERSION_CONFLICT", "Memory project bindings changed", 409)
    return result


def _confirm_impact(
    source: ReviewMemorySource,
    bindings: list[ReviewMemoryProjectSource],
    acknowledged: list[int] | None,
) -> None:
    projects = _active_project_ids(bindings)
    if acknowledged is None:
        if any(item != source.project_id for item in projects):
            raise AppError(
                "MEMORY_SHARED_CONFIRMATION_REQUIRED",
                "Confirm all affected projects before changing shared memory",
                409,
            )
    elif sorted(acknowledged) != projects or len(acknowledged) != len(set(acknowledged)):
        raise AppError(
            "MEMORY_VERSION_CONFLICT", "Affected projects changed; reload impact preview", 409
        )


def _locked_source(
    db: Session,
    project_id: int,
    source_id: int,
    version: int,
    acknowledged: list[int] | None = None,
) -> ReviewMemorySource:
    source, bindings = _lock_source_group(db, project_id, source_id)[source_id]
    assert_version(source.version, version)
    _require_manageable(source)
    if not any(row.project_id == project_id for row in bindings):
        raise AppError(
            "MEMORY_BINDING_MISSING", "Memory project binding is missing; check migration", 409
        )
    _confirm_impact(source, bindings, acknowledged)
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


def _validate_project_budgets(db: Session, project_ids: list[int]) -> None:
    for project_id in sorted(set(project_ids)):
        try:
            validate_core_budget(get_project_core_items(db, project_id, lock=True))
        except AppError as exception:
            raise AppError(
                exception.code, f"Project {project_id}: {exception.message}", exception.status_code
            ) from exception


def _finish_mutation(
    db: Session, source: ReviewMemorySource, *, budget: bool = True
) -> MemorySourceDetail:
    db.flush()
    if budget:
        _validate_project_budgets(
            db, _active_project_ids(repository.list_source_bindings(db, source.id, lock=True))
        )
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
    if metadata.replacement_of_id is not None:
        old, _ = _lock_source_group(db, project_id, metadata.replacement_of_id)[
            metadata.replacement_of_id
        ]
        assert_version(old.version, metadata.expected_replaced_version)
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
    source.parser_version = parsed.parser_version
    source.parse_warnings_json = json.dumps(warnings, ensure_ascii=False)
    source.replacement_of_id = metadata.replacement_of_id
    db.flush()
    return get_project_source(db, project_id, source.id)


def update_source(
    db: Session, project_id: int, source_id: int, request: MemorySourceUpdate
) -> MemorySourceDetail:
    source = _locked_source(
        db, project_id, source_id, request.expected_version, request.acknowledged_project_ids
    )
    if request.visibility is not None:
        if request.visibility == SourceVisibility.SHARED and (
            source.kind not in {MemoryKind.STANDARD, MemoryKind.ARCHITECTURE, MemoryKind.SKILL}
            or source.origin == MemoryOrigin.FEEDBACK
        ):
            raise AppError(
                "MEMORY_SHARING_INVALID", "Cases and feedback memories cannot be shared", 409
            )
        if request.visibility == SourceVisibility.PROJECT and any(
            row.project_id != project_id and row.state == BindingState.ACTIVE
            for row in repository.list_source_bindings(db, source_id, lock=True)
        ):
            raise AppError(
                "MEMORY_SHARING_IN_USE",
                "Detach other projects before making this source private",
                409,
            )
        source.visibility = request.visibility
    source.title, source.description = request.title, request.description
    _touch(source)
    return _finish_mutation(db, source)


def add_entry(
    db: Session, project_id: int, source_id: int, request: MemoryEntryCreate
) -> MemorySourceDetail:
    source = _locked_source(
        db, project_id, source_id, request.expected_source_version, request.acknowledged_project_ids
    )
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
    source = _locked_source(
        db, project_id, source_id, request.expected_source_version, request.acknowledged_project_ids
    )
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
    group = _lock_source_group(db, project_id, source_id, replacement=True)
    source, bindings = group[source_id]
    assert_version(source.version, request.expected_version)
    _require_manageable(source)
    if not any(row.project_id == project_id for row in bindings):
        raise AppError(
            "MEMORY_BINDING_MISSING", "Memory project binding is missing; check migration", 409
        )
    pending_replacement = source.replacement_of_id is not None and source.confirmed_at is None
    if not pending_replacement:
        _confirm_impact(source, bindings, request.acknowledged_project_ids)
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
    if pending_replacement:
        if request.expected_replaced_version is None:
            raise AppError(
                "MEMORY_REPLACEMENT_VERSION_REQUIRED", "expectedReplacedVersion is required", 409
            )
        old, old_bindings = group[source.replacement_of_id]
        assert_version(old.version, request.expected_replaced_version)
        _require_manageable(old)
        _confirm_impact(old, old_bindings, request.acknowledged_project_ids)
        if old.kind != source.kind or old.id == source.id:
            raise AppError("MEMORY_REPLACEMENT_INVALID", "Invalid replacement source", 409)
        if not any(row.project_id == project_id for row in old_bindings) or any(
            row.project_id != project_id for row in bindings
        ):
            raise AppError(
                "MEMORY_REPLACEMENT_INVALID", "Replacement project bindings are invalid", 409
            )
        by_project = {row.project_id: row for row in bindings}
        for old_binding in old_bindings:
            new_binding = by_project.get(old_binding.project_id)
            if new_binding is None:
                new_binding = ReviewMemoryProjectSource(
                    project_id=old_binding.project_id,
                    source_id=source.id,
                    version=1,
                )
                db.add(new_binding)
            else:
                new_binding.version += 1
            new_binding.state = old_binding.state
            new_binding.target_type = old_binding.target_type
            new_binding.path_globs_json = old_binding.path_globs_json
            new_binding.updated_at = utc_now()
        source.visibility = old.visibility
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
    db: Session,
    project_id: int,
    source_id: int,
    expected_version: int,
    state: SourceState,
    acknowledged_project_ids: list[int] | None = None,
) -> MemorySourceDetail:
    source = _locked_source(db, project_id, source_id, expected_version, acknowledged_project_ids)
    validate_source_transition(SourceState(source.state), state)
    if state not in {SourceState.DISABLED, SourceState.DELETED}:
        raise AppError("MEMORY_STATE_CONFLICT", "Use publish to activate memory", 409)
    source.state = state
    if state == SourceState.DELETED:
        source.deleted_at = utc_now()
    _touch(source)
    return _finish_mutation(db, source, budget=False)


def get_original(db: Session, project_id: int | None, source_id: int) -> tuple[str, bytes]:
    source = _readable_source(db, project_id, source_id)
    if source.original_filename is None or source.original_bytes is None:
        raise AppError("RESOURCE_NOT_FOUND", "Memory source has no original file", 404)
    if (project_id is None or project_id != source.project_id) and any(
        entry.state != EntryState.ACTIVE
        for entry in repository.list_entries(db, source.project_id, source_id)
    ):
        raise AppError(
            "MEMORY_ORIGINAL_NOT_PUBLISHED",
            "Original contains unpublished or disabled sections; use the published preview",
            409,
        )
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
        # Stored versions are signed MySQL INTs. Reserve their full width so a binding
        # update (for example 9 -> 10) cannot make another project's CORE overflow.
        budget_items = [
            item.model_copy(update={"source_version": 2147483647, "entry_version": 2147483647})
            for item in applicable
        ]
        size = len(render_core_context(budget_items).encode("utf-8"))
        if len(applicable) > MAX_CORE_ENTRIES or size > MAX_CORE_BYTES:
            raise AppError(
                "MEMORY_CORE_BUDGET_EXCEEDED",
                f"CORE budget exceeds 20 entries or 8000 bytes for {target}",
                409,
            )
        sizes[target] = size
    return sizes


def _binding_summary(record: ReviewMemoryProjectSource) -> MemoryBindingSummary:
    return MemoryBindingSummary(
        id=record.id,
        project_id=record.project_id,
        state=record.state,
        version=record.version,
        target_type=record.target_type,
        path_globs=_string_list(record.path_globs_json),
    )


def _source_summary(
    record: ReviewMemorySource,
    binding: ReviewMemoryProjectSource | None = None,
    can_manage: bool = False,
) -> MemorySourceSummary:
    return MemorySourceSummary(
        id=record.id,
        project_id=record.project_id,
        asset_scope="LIBRARY" if record.project_id is None else "PROJECT",
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
        visibility=record.visibility,
        binding=_binding_summary(binding) if binding is not None else None,
        can_manage=can_manage
        and record.state != SourceState.DELETED
        and record.origin != MemoryOrigin.FEEDBACK,
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
