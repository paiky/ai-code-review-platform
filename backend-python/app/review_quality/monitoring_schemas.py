from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


Engine = Literal["AGENT", "STANDARD"]
IssuePriority = Literal["HIGH", "MEDIUM", "LOW"]
IssueStatus = Literal["PENDING_REVIEW", "CONFIRMED", "VERIFYING", "CLOSED", "DISMISSED"]
ReportSource = Literal["MANUAL", "SCHEDULED"]
ReportStatus = Literal["RUNNING", "SUCCEEDED", "FAILED"]
SafeKey = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")]
RecordId = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
ReleaseSha = Annotated[str, Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
ResponseData = TypeVar("ResponseData")


class CreateMonitoringReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    startAt: AwareDatetime
    endAt: AwareDatetime
    idempotencyKey: str = Field(min_length=1, max_length=128, pattern=r"^[!-~]+$")

    @field_validator("startAt", "endAt", mode="before")
    @classmethod
    def require_iso_date(cls, value: object) -> object:
        if not isinstance(value, str) or "T" not in value:
            raise ValueError("expected a timezone-aware ISO date and time")
        return value


class UpdateMonitoringIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: int = Field(strict=True, ge=1, le=2**31 - 1)
    status: IssueStatus | None = None
    assignee: str | None = Field(default=None, max_length=128)
    resolution: str | None = Field(default=None, max_length=2048)
    acceptanceCriteria: str | None = Field(default=None, max_length=2048)
    evaluationCaseId: RecordId | None = None
    evaluationRunId: RecordId | None = None

    @field_validator("assignee", "resolution", "acceptanceCriteria")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is not None and any(ord(char) < 32 and char not in "\n\r\t" for char in value):
            raise ValueError("text contains control characters")
        return value or None

    @model_validator(mode="after")
    def require_change(self) -> "UpdateMonitoringIssue":
        if not self.model_fields_set - {"version"}:
            raise ValueError("provide at least one issue field to update")
        if self.status is None and "status" in self.model_fields_set:
            raise ValueError("status cannot be null")
        return self


class MonitoringMetric(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    engine: Engine
    key: SafeKey
    label: str = Field(min_length=1, max_length=128)
    eligibleCount: int = Field(ge=0)
    observedCount: int = Field(ge=0)
    unknownCount: int = Field(ge=0)
    value: int | float | None
    unit: Literal["COUNT", "RATIO", "BYTES", "MS", "CHARS", "ROWS"]
    group: Literal["MR", "PUSH", "MANUAL", "OTHER", "STANDARD"] | None = None


class MonitoringSample(BaseModel):
    taskId: RecordId
    reviewKey: str | None = Field(default=None, min_length=1, max_length=64)
    runId: RecordId | None = None
    eventId: RecordId | None = None


class MonitoringIssueDraft(BaseModel):
    engine: Engine
    issueType: SafeKey
    diagnosticType: SafeKey = "UNKNOWN"
    priority: IssuePriority = "MEDIUM"
    title: str = Field(min_length=1, max_length=255)
    affectedTaskCount: int = Field(ge=1)
    eventCount: int = Field(ge=1)
    observedCount: int = Field(ge=0)
    firstSeenAt: datetime
    lastSeenAt: datetime
    samples: list[MonitoringSample] = Field(max_length=10)


class MonitoringIssueSnapshot(MonitoringIssueDraft):
    issueId: RecordId


class MonitoringRelease(BaseModel):
    backendRelease: ReleaseSha
    workerRelease: ReleaseSha | None = None
    count: int = Field(ge=1)


class MonitoringReleaseCohort(BaseModel):
    engine: Engine
    status: Literal["KNOWN", "MIXED", "UNKNOWN"]
    eligibleCount: int = Field(ge=0)
    observedCount: int = Field(ge=0)
    releases: list[MonitoringRelease] = Field(max_length=10)

    @model_validator(mode="after")
    def validate_coverage(self) -> "MonitoringReleaseCohort":
        listed_count = sum(item.count for item in self.releases)
        if not listed_count <= self.observedCount <= self.eligibleCount:
            raise ValueError("invalid release coverage counts")
        if self.status == "KNOWN" and not (
            len(self.releases) == 1 and 0 < listed_count == self.observedCount == self.eligibleCount
        ):
            raise ValueError("known release cohort requires one release with full coverage")
        if self.status == "MIXED" and not (
            len(self.releases) > 1 and self.observedCount == self.eligibleCount
        ):
            raise ValueError("mixed release cohort requires multiple releases with full coverage")
        if any((item.workerRelease is not None) != (self.engine == "AGENT") for item in self.releases):
            raise ValueError("unexpected worker release for the cohort engine")
        return self


class MonitoringCollection(BaseModel):
    metrics: list[MonitoringMetric] = Field(max_length=250)
    issues: list[MonitoringIssueDraft] = Field(max_length=80)
    truncated: bool = False
    releaseCohorts: list[MonitoringReleaseCohort] = Field(default_factory=list, max_length=2)


class MonitoringSnapshot(BaseModel):
    metrics: list[MonitoringMetric]
    issues: list[MonitoringIssueSnapshot]
    truncated: bool
    releaseCohorts: list[MonitoringReleaseCohort] = Field(default_factory=list, max_length=2)


class MonitoringReportResponse(BaseModel):
    id: RecordId
    projectId: RecordId
    source: ReportSource
    startAt: AwareDatetime
    endAt: AwareDatetime
    status: ReportStatus
    ruleVersion: str
    createdAt: AwareDatetime
    updatedAt: AwareDatetime
    finishedAt: AwareDatetime | None
    errorCode: str | None
    snapshot: MonitoringSnapshot | None


class MonitoringReportList(BaseModel):
    items: list[MonitoringReportResponse]
    total: int
    pageNo: int
    pageSize: int


class MonitoringIssueResponse(BaseModel):
    id: RecordId
    projectId: RecordId
    engine: Engine
    issueType: SafeKey
    diagnosticType: SafeKey
    title: str
    priority: IssuePriority
    firstSeenAt: AwareDatetime
    lastSeenAt: AwareDatetime
    lastReportId: RecordId
    status: IssueStatus
    version: int
    assignee: str | None
    resolution: str | None
    acceptanceCriteria: str | None
    evaluationCaseId: RecordId | None
    evaluationRunId: RecordId | None
    closedAt: AwareDatetime | None


class MonitoringResponseEnvelope(BaseModel, Generic[ResponseData]):
    success: bool
    code: str
    message: str
    data: ResponseData
    traceId: str | None
