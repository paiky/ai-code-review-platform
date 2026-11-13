from collections.abc import Generator
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import Field, ValidationError
from python_multipart.exceptions import MultipartParseError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.core.errors import AppError
from app.core.response import ok
from app.review_memory import service
from app.review_memory import feedback as memory_feedback
from app.review_memory import settings as memory_settings
from app.review_memory.summary import get_run_memory_summary
from app.review_memory.parsing import (
    MAX_METADATA_BYTES,
    MAX_REQUEST_BYTES,
    parse_upload,
    upload_byte_limit,
)
from app.review_memory.schemas import (
    MemoryApiResponse,
    MemoryBindingResult,
    MemoryBindingUpdate,
    MemoryEntryCreate,
    MemoryEntryUpdate,
    MemoryPublish,
    MemorySourceDetail,
    MemorySourceImpact,
    MemorySourceDisable,
    MemorySourceDraft,
    MemorySourcePage,
    MemorySourceQuery,
    MemorySourceUpdate,
    MemorySharedQuery,
    MemoryCaseConfirmation,
    MemoryFeedbackDetail,
    MemoryFeedbackPage,
    MemoryFeedbackQuery,
    MemoryWritebackSummary,
    MemoryUploadMetadata,
    SourceState,
    MemorySettings,
    MemorySettingsUpdate,
    MemoryRunSummary,
)


router = APIRouter(prefix="/api/projects/{project_id}/review-memory", tags=["review-memory"])
shared_router = APIRouter(prefix="/api/review-memory/shared-sources", tags=["review-memory"])
run_router = APIRouter(prefix="/api/agent-review/runs", tags=["review-memory"])
DetailResponse = MemoryApiResponse[MemorySourceDetail]


@router.get("/settings", response_model=MemoryApiResponse[MemorySettings])
def get_memory_settings(project_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(memory_settings.read_settings(db, project_id))


@router.put("/settings", response_model=MemoryApiResponse[MemorySettings])
def update_memory_settings(
    project_id: int, request: MemorySettingsUpdate, db: Session = Depends(get_db)
) -> dict:
    try:
        result = memory_settings.update_settings(db, project_id, request)
        db.commit()
        return ok(result)
    except Exception:
        db.rollback()
        raise


@run_router.get("/{run_id}/memory-summary", response_model=MemoryApiResponse[MemoryRunSummary])
def get_memory_summary(
    run_id: int,
    project_id: int = Query(alias="projectId", gt=0),
    db: Session = Depends(get_db),
) -> dict:
    return ok(get_run_memory_summary(db, run_id, project_id))


@router.get("/feedbacks", response_model=MemoryApiResponse[MemoryFeedbackPage])
def list_memory_feedbacks(
    project_id: int,
    query: Annotated[MemoryFeedbackQuery, Query()],
    db: Session = Depends(get_db),
) -> dict:
    return ok(memory_feedback.list_feedbacks(db, project_id, query))


@router.get("/feedbacks/{feedback_id}", response_model=MemoryApiResponse[MemoryFeedbackDetail])
def get_memory_feedback(project_id: int, feedback_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(memory_feedback.get_feedback_detail(db, project_id, feedback_id))


@router.post(
    "/feedbacks/{feedback_id}/confirm",
    status_code=202,
    response_model=MemoryApiResponse[MemoryWritebackSummary],
)
def confirm_memory_feedback(
    project_id: int,
    feedback_id: int,
    request: MemoryCaseConfirmation,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = memory_feedback.confirm_feedback(db, project_id, feedback_id, request)
        db.commit()
        return ok(result)
    except Exception:
        db.rollback()
        raise


@router.get("/writebacks/{writeback_id}", response_model=MemoryApiResponse[MemoryWritebackSummary])
def get_memory_writeback(project_id: int, writeback_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(service.get_project_writeback(db, project_id, writeback_id))


def memory_db(db: Session = Depends(get_db)) -> Generator[Session, None, None]:
    try:
        yield db
    except Exception:
        db.rollback()
        raise


def _commit(db: Session, detail: MemorySourceDetail | MemoryBindingResult) -> dict:
    db.commit()
    return ok(detail)


def _import_upload(
    db: Session,
    project_id: int,
    filename: str | None,
    content_type: str | None,
    original: bytes,
    metadata: MemoryUploadMetadata,
) -> dict:
    service.require_project(db, project_id)
    parsed = parse_upload(filename, content_type, original, metadata)
    return _commit(db, service.create_upload_draft(db, project_id, parsed, original, metadata))


@router.get("/sources", response_model=MemoryApiResponse[MemorySourcePage])
def list_sources(
    project_id: int,
    query: Annotated[MemorySourceQuery, Query()],
    db: Session = Depends(memory_db),
) -> dict:
    return ok(service.list_project_sources(db, project_id, query))


@shared_router.get("", response_model=MemoryApiResponse[MemorySourcePage])
def list_shared_sources(
    query: Annotated[MemorySharedQuery, Query()],
    db: Session = Depends(memory_db),
) -> dict:
    return ok(service.list_shared_sources(db, query))


@shared_router.get("/{source_id}", response_model=DetailResponse)
def get_shared_source(source_id: int, db: Session = Depends(memory_db)) -> dict:
    return ok(service.get_shared_source(db, source_id))


@shared_router.get("/{source_id}/original", response_class=Response)
def download_shared_original(source_id: int, db: Session = Depends(memory_db)) -> Response:
    return _original_response(*service.get_original(db, None, source_id))


@router.get("/sources/{source_id}/impact", response_model=MemoryApiResponse[MemorySourceImpact])
def get_source_impact(project_id: int, source_id: int, db: Session = Depends(memory_db)) -> dict:
    return ok(service.get_source_impact(db, project_id, source_id))


@router.get("/sources/{source_id}/binding", response_model=MemoryApiResponse[MemoryBindingResult])
def get_source_binding(project_id: int, source_id: int, db: Session = Depends(memory_db)) -> dict:
    return ok(service.get_source_binding(db, project_id, source_id))


@router.put("/sources/{source_id}/binding", response_model=MemoryApiResponse[MemoryBindingResult])
def update_source_binding(
    project_id: int,
    source_id: int,
    request: MemoryBindingUpdate,
    db: Session = Depends(memory_db),
) -> dict:
    return _commit(db, service.update_source_binding(db, project_id, source_id, request))


@router.post("/sources", response_model=DetailResponse)
def create_source(
    project_id: int, request: MemorySourceDraft, db: Session = Depends(memory_db)
) -> dict:
    return _commit(db, service.create_manual_draft(db, project_id, request))


class _RequestTooLarge(MultiPartException):
    pass


class _MemoryMultipartParser(MultiPartParser):
    """Also close partial files on malformed input and client disconnects."""

    ended = False

    def on_end(self) -> None:
        self.ended = True
        super().on_end()

    async def parse(self):
        try:
            form = await super().parse()
            if not self.ended:
                raise MultiPartException("Multipart body is incomplete")
            return form
        except BaseException:
            # Starlette only cleans this list for MultiPartException, not parser/disconnect errors.
            for file in self._files_to_close_on_error:
                file.close()
            raise


UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file", "metadata"],
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                            "description": "MD/TXT/SKILL.md <= 1 MiB; DOCX/text PDF <= 5 MiB",
                        },
                        "metadata": {
                            "type": "string",
                            "description": "MemoryUploadMetadata JSON; up to 16 KiB",
                        },
                    },
                    "additionalProperties": False,
                }
            }
        },
    },
}


@router.post("/uploads", response_model=DetailResponse, openapi_extra=UPLOAD_BODY)
async def upload_source(
    project_id: int, request: Request, db: Session = Depends(memory_db)
) -> dict:
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "multipart/form-data":
        raise AppError("MEMORY_FORMAT_UNSUPPORTED", "Upload requires multipart/form-data", 415)

    async def bounded_stream():
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_REQUEST_BYTES:
                # MultiPartParser closes spooled files on this exception, including partial files.
                raise _RequestTooLarge("Upload request exceeds bounded size")
            yield chunk

    try:
        form = await _MemoryMultipartParser(
            request.headers,
            bounded_stream(),
            max_files=1,
            max_fields=1,
            max_part_size=MAX_METADATA_BYTES,
        ).parse()
    except _RequestTooLarge as exception:
        raise AppError(
            "MEMORY_UPLOAD_TOO_LARGE", "Request exceeds 5 MiB + 64 KiB", 413
        ) from exception
    except MultiPartException as exception:
        status = 413 if "maximum size" in exception.message else 400
        raise AppError(
            "MEMORY_MULTIPART_INVALID", "Expected one file and one bounded metadata field", status
        ) from exception
    except (MultipartParseError, ValueError) as exception:
        raise AppError(
            "MEMORY_MULTIPART_INVALID", "Invalid multipart structure", 400
        ) from exception
    try:
        items = form.multi_items()
        if len(items) != 2 or {key for key, _ in items} != {"file", "metadata"}:
            raise AppError("MEMORY_MULTIPART_INVALID", "Expected exactly file and metadata", 400)
        file, raw_metadata = form["file"], form["metadata"]
        if not isinstance(file, UploadFile) or not isinstance(raw_metadata, str):
            raise AppError("MEMORY_MULTIPART_INVALID", "Invalid file or metadata field", 400)
        if len(raw_metadata.encode("utf-8")) > MAX_METADATA_BYTES:
            raise AppError("MEMORY_METADATA_TOO_LARGE", "Metadata exceeds 16 KiB", 413)
        try:
            metadata = MemoryUploadMetadata.model_validate_json(raw_metadata)
        except ValidationError as exception:
            raise AppError(
                "VALIDATION_ERROR", "metadata does not match MemoryUploadMetadata", 400
            ) from exception
        original = await file.read(upload_byte_limit(file.filename) + 1)
        return await run_in_threadpool(
            _import_upload, db, project_id, file.filename, file.content_type, original, metadata
        )
    finally:
        await form.close()


@router.get("/sources/{source_id}", response_model=DetailResponse)
def get_source(project_id: int, source_id: int, db: Session = Depends(memory_db)) -> dict:
    return ok(service.get_project_source(db, project_id, source_id))


@router.get("/sources/{source_id}/original", response_class=Response)
def download_original(
    project_id: int, source_id: int, db: Session = Depends(memory_db)
) -> Response:
    return _original_response(*service.get_original(db, project_id, source_id))


def _original_response(filename: str, content: bytes) -> Response:
    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.put("/sources/{source_id}", response_model=DetailResponse)
def update_source(
    project_id: int, source_id: int, request: MemorySourceUpdate, db: Session = Depends(memory_db)
) -> dict:
    return _commit(db, service.update_source(db, project_id, source_id, request))


@router.post("/sources/{source_id}/entries", response_model=DetailResponse)
def create_entry(
    project_id: int, source_id: int, request: MemoryEntryCreate, db: Session = Depends(memory_db)
) -> dict:
    return _commit(db, service.add_entry(db, project_id, source_id, request))


@router.put("/sources/{source_id}/entries/{entry_id}", response_model=DetailResponse)
def update_entry(
    project_id: int,
    source_id: int,
    entry_id: int,
    request: MemoryEntryUpdate,
    db: Session = Depends(memory_db),
) -> dict:
    return _commit(db, service.update_entry(db, project_id, source_id, entry_id, request))


@router.post("/sources/{source_id}/publish", response_model=DetailResponse)
def publish_source(
    project_id: int, source_id: int, request: MemoryPublish, db: Session = Depends(memory_db)
) -> dict:
    return _commit(db, service.publish_source(db, project_id, source_id, request))


@router.put("/sources/{source_id}/state", response_model=DetailResponse)
def disable_source(
    project_id: int, source_id: int, request: MemorySourceDisable, db: Session = Depends(memory_db)
) -> dict:
    return _commit(
        db,
        service.change_source_state(
            db,
            project_id,
            source_id,
            request.expected_version,
            SourceState.DISABLED,
            request.acknowledged_project_ids,
        ),
    )


@router.delete("/sources/{source_id}", response_model=DetailResponse)
def delete_source(
    project_id: int,
    source_id: int,
    expected_version: int = Query(alias="expectedVersion", gt=0),
    acknowledged_project_ids: list[Annotated[int, Field(gt=0)]] | None = Query(
        default=None,
        alias="acknowledgedProjectIds",
        max_length=1000,
    ),
    db: Session = Depends(memory_db),
) -> dict:
    return _commit(
        db,
        service.change_source_state(
            db,
            project_id,
            source_id,
            expected_version,
            SourceState.DELETED,
            acknowledged_project_ids,
        ),
    )
