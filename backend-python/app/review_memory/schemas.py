from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.project_integration.schemas import TargetType


MAX_SOURCE_ENTRIES = 200
MAX_SOURCE_CONTENT_BYTES = 256 * 1024
MAX_ENTRY_CONTENT_BYTES = 4000
MAX_CORE_ENTRIES = 20
MAX_CORE_BYTES = 8000


class MemoryKind(StrEnum):
    STANDARD = "STANDARD"
    SKILL = "SKILL"
    PITFALL = "PITFALL"
    ARCHITECTURE = "ARCHITECTURE"
    INCIDENT = "INCIDENT"


class MemoryOrigin(StrEnum):
    MANUAL = "MANUAL"
    UPLOAD = "UPLOAD"
    FEEDBACK = "FEEDBACK"


class SourceState(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    DISABLED = "DISABLED"
    DELETED = "DELETED"


class EntryState(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class SourceVisibility(StrEnum):
    PROJECT = "PROJECT"
    SHARED = "SHARED"


class BindingState(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class LoadMode(StrEnum):
    CORE = "CORE"
    ON_DEMAND = "ON_DEMAND"


class IssueType(StrEnum):
    GENERAL = "GENERAL"
    API_CONTRACT = "API_CONTRACT"
    DATABASE = "DATABASE"
    CACHE = "CACHE"
    MQ = "MQ"
    TRANSACTION = "TRANSACTION"
    SECURITY = "SECURITY"
    CONFIG = "CONFIG"
    ERROR_HANDLING = "ERROR_HANDLING"
    TESTING = "TESTING"


class WritebackState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED_STALE_SOURCE = "CANCELLED_STALE_SOURCE"


class MemorySchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=False)


class MemorySettings(MemorySchema):
    enabled: bool
    version: int = Field(ge=1)
    schema_ready: bool = Field(alias="schemaReady")


class MemorySettingsUpdate(MemorySchema):
    enabled: bool = Field(strict=True)
    expected_version: int = Field(alias="expectedVersion", gt=0, strict=True)


class MemorySelectedSummary(MemorySchema):
    source_id: int = Field(alias="sourceId", gt=0)
    entry_id: int = Field(alias="entryId", gt=0)
    binding_id: int = Field(alias="bindingId", gt=0)
    owner_project_id: int = Field(alias="ownerProjectId", gt=0)
    source_version: int = Field(alias="sourceVersion", gt=0)
    entry_version: int = Field(alias="entryVersion", gt=0)
    binding_version: int = Field(alias="bindingVersion", gt=0)
    kind: MemoryKind
    load_mode: LoadMode = Field(alias="loadMode")
    content_hash: str = Field(alias="contentHash", pattern=r"^[a-f0-9]{64}$")
    title: str = Field(max_length=160)
    applicability: str = Field(max_length=160)
    selection_reason: list[
        Literal["CORE_REQUIRED", "ON_DEMAND", "ISSUE_MATCH", "PATH_MATCH", "KEYWORD_MATCH"]
    ] = Field(alias="selectionReason", max_length=8)
    path_sample: str | None = Field(alias="pathSample", default=None, max_length=160)
    path_count: int = Field(alias="pathCount", ge=0)


class MemorySnapshot(MemorySchema):
    schema_version: Literal["review-memory-v1"] = Field(
        default="review-memory-v1", alias="schemaVersion"
    )
    policy_version: int = Field(alias="policyVersion", ge=1)
    project_id: int = Field(alias="projectId", gt=0)
    target_type: TargetType | None = Field(alias="targetType")
    lookup_status: Literal["DISABLED", "EMPTY", "NO_MATCH", "LOADED", "PARTIAL_LOOKUP"] = Field(
        alias="lookupStatus"
    )
    disabled_reason: Literal["PROJECT_DISABLED", "SCHEMA_PENDING"] | None = Field(
        default=None, alias="disabledReason"
    )
    selected: list[MemorySelectedSummary] = Field(default_factory=list, max_length=28)
    injected_bytes: int = Field(default=0, alias="injectedBytes", ge=0, le=14000)
    skip_reasons: dict[str, int] = Field(default_factory=dict, alias="skipReasons")
    issue_hints_unknown: bool = Field(default=False, alias="issueHintsUnknown")
    candidate_scan_limited: bool = Field(default=False, alias="candidateScanLimited")


class MemoryRunSummary(MemorySchema):
    run_id: int = Field(alias="runId")
    project_id: int = Field(alias="projectId")
    recorded: bool
    snapshot: MemorySnapshot | None = None
    effective_engine: str | None = Field(alias="effectiveEngine")
    adoption: Literal[
        "HISTORICAL", "PENDING", "AGENT", "NOT_LOADED", "STANDARD_FALLBACK", "UNAVAILABLE"
    ]


class MemoryEntryDraft(MemorySchema):
    heading: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=MAX_SOURCE_CONTENT_BYTES)
    target_type: TargetType | None = Field(default=None, alias="targetType")
    issue_type: IssueType | None = Field(default=None, alias="issueType")
    path_globs: list[str] = Field(default_factory=list, alias="pathGlobs", max_length=8)
    keywords: list[str] = Field(default_factory=list, max_length=12)
    load_mode: LoadMode = Field(default=LoadMode.ON_DEMAND, alias="loadMode")

    @field_validator("heading")
    @classmethod
    def validate_heading(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("heading must not be blank")
        return value.strip()

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("content must not be blank or contain NUL")
        if len(value.encode("utf-8")) > MAX_SOURCE_CONTENT_BYTES:
            raise ValueError("draft content exceeds 256 KiB")
        return value

    @field_validator("path_globs")
    @classmethod
    def validate_path_globs(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            pattern = value.strip().replace("\\", "/")
            if (
                not pattern
                or len(pattern) > 256
                or PurePosixPath(pattern).is_absolute()
                or PureWindowsPath(pattern).drive
                or any(part in {"", ".", ".."} for part in pattern.split("/"))
                or ":" in pattern
                or any(ord(char) < 32 for char in pattern)
            ):
                raise ValueError("pathGlobs must contain relative, non-traversing patterns")
            if pattern not in normalized:
                normalized.append(pattern)
        return normalized

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            keyword = value.strip()
            if not keyword or len(keyword) > 64 or any(ord(char) < 32 for char in keyword):
                raise ValueError("keywords must contain 1 to 64 characters without controls")
            if keyword not in normalized:
                normalized.append(keyword)
        return normalized


class MemorySourceDraft(MemorySchema):
    kind: MemoryKind
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    entries: list[MemoryEntryDraft] = Field(default_factory=list, max_length=MAX_SOURCE_ENTRIES)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_source(self) -> "MemorySourceDraft":
        if (
            sum(len(entry.content.encode("utf-8")) for entry in self.entries)
            > MAX_SOURCE_CONTENT_BYTES
        ):
            raise ValueError("source content exceeds 256 KiB")
        if self.kind not in {MemoryKind.STANDARD, MemoryKind.ARCHITECTURE}:
            if any(entry.load_mode == LoadMode.CORE for entry in self.entries):
                raise ValueError("CORE is only allowed for STANDARD or ARCHITECTURE")
        return self


class MemorySourceQuery(MemorySchema):
    view: Literal["OWNED", "USED"] = "OWNED"
    kind: MemoryKind | None = None
    state: SourceState | None = None
    target_type: TargetType | None = Field(default=None, alias="targetType")
    issue_type: IssueType | None = Field(default=None, alias="issueType")
    keyword: str | None = Field(default=None, max_length=128)
    page_no: int = Field(default=1, alias="pageNo", ge=1)
    page_size: int = Field(default=20, alias="pageSize", ge=1, le=100)

    @field_validator("keyword")
    @classmethod
    def normalize_keyword(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class MemoryEntryResponse(MemoryEntryDraft):
    id: int
    source_id: int = Field(alias="sourceId")
    section_key: str = Field(alias="sectionKey")
    ordinal: int
    state: EntryState
    version: int
    content_sha256: str = Field(alias="contentSha256")
    validation_errors: list[str] = Field(default_factory=list, alias="validationErrors")


class MemoryLibraryQuery(MemorySchema):
    owner_project_id: int | None = Field(default=None, alias="ownerProjectId", gt=0)
    using_project_id: int | None = Field(default=None, alias="usingProjectId", gt=0)
    category: Literal["DOCUMENT", "CASE"] | None = None
    kind: MemoryKind | None = None
    state: SourceState | None = None
    target_type: TargetType | None = Field(default=None, alias="targetType")
    issue_type: IssueType | None = Field(default=None, alias="issueType")
    keyword: str | None = Field(default=None, max_length=128)
    page_no: int = Field(default=1, alias="pageNo", ge=1)
    page_size: int = Field(default=20, alias="pageSize", ge=1, le=100)

    _keyword = field_validator("keyword")(MemorySourceQuery.normalize_keyword.__func__)


class MemoryBindingQuery(MemorySchema):
    state: BindingState = BindingState.ACTIVE
    page_no: int = Field(default=1, alias="pageNo", ge=1)
    page_size: int = Field(default=20, alias="pageSize", ge=1, le=100)


class MemoryBindingSummary(MemorySchema):
    id: int
    project_id: int = Field(alias="projectId")
    state: BindingState
    version: int
    target_type: TargetType | None = Field(alias="targetType")
    path_globs: list[str] = Field(default_factory=list, alias="pathGlobs")


class MemoryBindingUpdate(MemorySchema):
    expected_source_version: int = Field(alias="expectedSourceVersion", gt=0, strict=True)
    expected_binding_version: int | None = Field(
        default=None, alias="expectedBindingVersion", gt=0, strict=True
    )
    state: BindingState
    target_type: TargetType | None = Field(default=None, alias="targetType")
    path_globs: list[str] = Field(default_factory=list, alias="pathGlobs", max_length=8)

    _paths = field_validator("path_globs")(MemoryEntryDraft.validate_path_globs.__func__)


class MemoryBindingResult(MemorySchema):
    source_version: int = Field(alias="sourceVersion")
    binding: MemoryBindingSummary


class MemorySourceImpact(MemorySchema):
    source_id: int = Field(alias="sourceId")
    source_version: int = Field(alias="sourceVersion")
    project_ids: list[int] = Field(alias="projectIds")
    bindings: list[MemoryBindingSummary]


class MemorySharedQuery(MemorySchema):
    kind: Literal["STANDARD", "ARCHITECTURE", "SKILL"] | None = None
    keyword: str | None = Field(default=None, max_length=128)
    page_no: int = Field(default=1, alias="pageNo", ge=1)
    page_size: int = Field(default=20, alias="pageSize", ge=1, le=100)

    _keyword = field_validator("keyword")(MemorySourceQuery.normalize_keyword.__func__)


class MemorySourceSummary(MemorySchema):
    id: int
    project_id: int = Field(alias="projectId")
    kind: MemoryKind
    origin: MemoryOrigin
    title: str
    description: str | None
    state: SourceState
    version: int
    source_feedback_id: int | None = Field(alias="sourceFeedbackId")
    replacement_of_id: int | None = Field(alias="replacementOfId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    visibility: SourceVisibility = SourceVisibility.PROJECT
    binding: MemoryBindingSummary | None = None
    can_manage: bool = Field(default=False, alias="canManage")


class MemorySourceDetail(MemorySourceSummary):
    entries: list[MemoryEntryResponse]
    original_filename: str | None = Field(default=None, alias="originalFilename")
    media_type: str | None = Field(default=None, alias="mediaType")
    parser_version: str | None = Field(default=None, alias="parserVersion")
    parse_warnings: list[str] = Field(default_factory=list, alias="parseWarnings")
    has_original: bool = Field(default=False, alias="hasOriginal")
    can_download_original: bool = Field(default=False, alias="canDownloadOriginal")
    confirmed_by: str | None = Field(default=None, alias="confirmedBy")
    confirmed_at: datetime | None = Field(default=None, alias="confirmedAt")
    identity_verified: bool = Field(default=False, alias="identityVerified")
    legacy_policy_ids: list[int] = Field(default_factory=list, alias="legacyPolicyIds")


class MemorySourcePage(MemorySchema):
    items: list[MemorySourceSummary]
    total: int
    page_no: int = Field(alias="pageNo")
    page_size: int = Field(alias="pageSize")


class MemoryLibrarySource(MemorySourceSummary):
    active_binding_count: int = Field(alias="activeBindingCount", ge=0)
    using_project_ids: list[int] = Field(alias="usingProjectIds", max_length=3)
    using_projects_truncated: bool = Field(alias="usingProjectsTruncated")
    target_types: list[TargetType] = Field(alias="targetTypes", max_length=6)
    has_unrestricted_target: bool = Field(alias="hasUnrestrictedTarget")
    has_entries: bool = Field(alias="hasEntries")


class MemoryLibraryPage(MemorySchema):
    items: list[MemoryLibrarySource]
    total: int
    page_no: int = Field(alias="pageNo")
    page_size: int = Field(alias="pageSize")


class MemorySourceProjectsPage(MemorySchema):
    source_id: int = Field(alias="sourceId")
    source_version: int = Field(alias="sourceVersion")
    items: list[MemoryBindingSummary]
    total: int
    page_no: int = Field(alias="pageNo")
    page_size: int = Field(alias="pageSize")


class MemoryProjectBinding(MemorySchema):
    source_id: int = Field(alias="sourceId")
    binding: MemoryBindingSummary
    source: MemorySourceSummary | None
    source_missing: bool = Field(alias="sourceMissing")
    has_active_entries: bool = Field(alias="hasActiveEntries")
    can_read_source: bool = Field(alias="canReadSource")


class MemoryProjectBindingsPage(MemorySchema):
    project_id: int = Field(alias="projectId")
    items: list[MemoryProjectBinding]
    total: int
    page_no: int = Field(alias="pageNo")
    page_size: int = Field(alias="pageSize")


class MemoryWritebackSummary(MemorySchema):
    id: int
    feedback_id: int = Field(alias="feedbackId")
    source_id: int | None = Field(alias="sourceId")
    state: WritebackState
    attempts: int
    last_error_code: str | None = Field(alias="lastErrorCode")


class MemoryFeedbackQuery(MemorySchema):
    feedback_type: Literal["FALSE_POSITIVE"] | None = Field(default=None, alias="feedbackType")
    status: Literal["PENDING", "VALID", "INSUFFICIENT", "IGNORED", "CONVERTED"] | None = None
    page_no: int = Field(default=1, alias="pageNo", ge=1)
    page_size: int = Field(default=20, alias="pageSize", ge=1, le=100)


class MemoryFeedbackSummary(MemorySchema):
    id: int
    project_id: int = Field(alias="projectId")
    task_id: int = Field(alias="taskId")
    review_key: str | None = Field(alias="reviewKey")
    item_fingerprint: str = Field(alias="itemFingerprint")
    risk_title: str | None = Field(alias="riskTitle")
    risk_type: str | None = Field(alias="riskType")
    feedback_type: str = Field(alias="feedbackType")
    reason_type: str | None = Field(alias="reasonType")
    reason_text: str | None = Field(alias="reasonText")
    status: str
    feedback_digest: str = Field(alias="feedbackDigest")
    memory_source_id: int | None = Field(alias="memorySourceId")
    source_version: int | None = Field(alias="sourceVersion")
    source_state: SourceState | None = Field(alias="sourceState")
    writeback_id: int | None = Field(alias="writebackId")
    writeback_state: WritebackState | None = Field(alias="writebackState")


class MemoryFeedbackDetail(MemoryFeedbackSummary):
    item_snapshot: dict[str, Any] = Field(alias="itemSnapshot")
    missing_context_types: list[str] = Field(alias="missingContextTypes")
    task_url: str = Field(alias="taskUrl")
    finding_available: bool = Field(alias="findingAvailable")


class MemoryFeedbackPage(MemorySchema):
    items: list[MemoryFeedbackSummary]
    total: int
    page_no: int = Field(alias="pageNo")
    page_size: int = Field(alias="pageSize")


class MemoryCaseConfirmation(MemorySchema):
    expected_feedback_digest: str = Field(alias="expectedFeedbackDigest", pattern=r"^[a-f0-9]{64}$")
    expected_source_version: int | None = Field(
        default=None, alias="expectedSourceVersion", gt=0, strict=True
    )
    title: str = Field(min_length=1, max_length=255)
    target_type: TargetType | None = Field(default=None, alias="targetType")
    issue_type: IssueType | None = Field(default=None, alias="issueType")
    path_globs: list[str] = Field(default_factory=list, alias="pathGlobs", max_length=8)
    keywords: list[str] = Field(default_factory=list, max_length=12)
    applicability: str = Field(min_length=1, max_length=4000)
    misjudgment_cause: str = Field(alias="misjudgmentCause", min_length=1, max_length=4000)
    correct_approach: str = Field(alias="correctApproach", min_length=1, max_length=4000)
    required_evidence: str = Field(alias="requiredEvidence", min_length=1, max_length=4000)
    exceptions: str = Field(min_length=1, max_length=4000)
    operator_name: str | None = Field(default=None, alias="operatorName", max_length=96)

    _paths = field_validator("path_globs")(MemoryEntryDraft.validate_path_globs.__func__)
    _keywords = field_validator("keywords")(MemoryEntryDraft.validate_keywords.__func__)

    @field_validator(
        "title",
        "applicability",
        "misjudgment_cause",
        "correct_approach",
        "required_evidence",
        "exceptions",
    )
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("case fields must not be blank or contain NUL")
        return value.strip()


class CoreBudgetItem(MemoryEntryDraft):
    source_id: int = Field(alias="sourceId", gt=0)
    entry_id: int = Field(alias="entryId", gt=0)
    source_version: int = Field(alias="sourceVersion", gt=0)
    entry_version: int = Field(alias="entryVersion", gt=0)
    source_kind: MemoryKind = Field(alias="sourceKind")
    source_title: str = Field(alias="sourceTitle", min_length=1, max_length=255)
    binding_path_globs: list[str] = Field(
        default_factory=list, alias="bindingPathGlobs", max_length=8
    )
    load_mode: LoadMode = Field(default=LoadMode.CORE, alias="loadMode")

    _binding_paths = field_validator("binding_path_globs")(
        MemoryEntryDraft.validate_path_globs.__func__
    )


class MemoryImpactConfirmation(MemorySchema):
    acknowledged_project_ids: list[Annotated[int, Field(gt=0, strict=True)]] | None = Field(
        default=None, alias="acknowledgedProjectIds", max_length=1000
    )

    @field_validator("acknowledged_project_ids")
    @classmethod
    def validate_project_ids(cls, values: list[int] | None) -> list[int] | None:
        if values is not None and len(values) != len(set(values)):
            raise ValueError("acknowledgedProjectIds must be unique")
        return sorted(values) if values is not None else None


class MemorySourceUpdate(MemoryImpactConfirmation):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    expected_version: int = Field(alias="expectedVersion", gt=0, strict=True)
    visibility: SourceVisibility | None = None

    _title = field_validator("title")(MemorySourceDraft.validate_title.__func__)


class MemoryEntryCreate(MemoryImpactConfirmation):
    expected_source_version: int = Field(alias="expectedSourceVersion", gt=0, strict=True)
    entry: MemoryEntryDraft


class MemoryEntryUpdate(MemoryImpactConfirmation):
    expected_source_version: int = Field(alias="expectedSourceVersion", gt=0, strict=True)
    expected_version: int = Field(alias="expectedVersion", gt=0, strict=True)
    entry: MemoryEntryDraft | None = None
    state: Literal["DISABLED"] | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> "MemoryEntryUpdate":
        if (self.entry is None) == (self.state is None):
            raise ValueError("provide either entry or state=DISABLED")
        return self


class MemorySelectedEntry(MemorySchema):
    id: int = Field(gt=0, strict=True)
    expected_version: int = Field(alias="expectedVersion", gt=0, strict=True)


class MemoryPublish(MemoryImpactConfirmation):
    expected_version: int = Field(alias="expectedVersion", gt=0, strict=True)
    selected_entries: list[MemorySelectedEntry] = Field(
        alias="selectedEntries", min_length=1, max_length=MAX_SOURCE_ENTRIES
    )
    expected_replaced_version: int | None = Field(
        default=None, alias="expectedReplacedVersion", gt=0, strict=True
    )
    operator_name: str | None = Field(default=None, alias="operatorName", max_length=96)

    @field_validator("selected_entries")
    @classmethod
    def validate_selected_entries(
        cls, values: list[MemorySelectedEntry]
    ) -> list[MemorySelectedEntry]:
        if len({value.id for value in values}) != len(values):
            raise ValueError("selectedEntries must have unique IDs")
        return values


class MemorySourceDisable(MemoryImpactConfirmation):
    expected_version: int = Field(alias="expectedVersion", gt=0, strict=True)
    state: Literal["DISABLED"]


class MemoryUploadMetadata(MemorySchema):
    kind: MemoryKind
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    target_type: TargetType | None = Field(default=None, alias="targetType")
    issue_type: IssueType | None = Field(default=None, alias="issueType")
    path_globs: list[str] = Field(default_factory=list, alias="pathGlobs", max_length=8)
    keywords: list[str] = Field(default_factory=list, max_length=12)
    load_mode: LoadMode = Field(default=LoadMode.ON_DEMAND, alias="loadMode")
    replacement_of_id: int | None = Field(default=None, alias="replacementOfId", gt=0, strict=True)
    expected_replaced_version: int | None = Field(
        default=None, alias="expectedReplacedVersion", gt=0, strict=True
    )

    @model_validator(mode="after")
    def validate_metadata(self) -> "MemoryUploadMetadata":
        if (self.replacement_of_id is None) != (self.expected_replaced_version is None):
            raise ValueError(
                "replacementOfId and expectedReplacedVersion must be provided together"
            )
        if self.title is not None:
            self.title = MemorySourceDraft.validate_title(self.title)
        # Apply the same label and kind rules used by manual drafts before parsing the file.
        entry = MemoryEntryDraft(
            heading="upload",
            content="upload",
            target_type=self.target_type,
            issue_type=self.issue_type,
            path_globs=self.path_globs,
            keywords=self.keywords,
            load_mode=self.load_mode,
        )
        self.path_globs, self.keywords = entry.path_globs, entry.keywords
        MemorySourceDraft(kind=self.kind, title="upload", entries=[entry])
        return self


ResponseData = TypeVar("ResponseData")


class MemoryApiResponse(MemorySchema, Generic[ResponseData]):
    success: bool
    code: str
    message: str
    data: ResponseData
    trace_id: str | None = Field(alias="traceId")
