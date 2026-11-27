from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.review_quality.monitoring_schemas import IssuePriority, RecordId


DecisionAction = Literal["REPLAY", "OBSERVE", "NEEDS_INPUT"]
AssessmentAction = Literal["OBSERVE", "NEEDS_INPUT"]
ReplayKind = Literal["AGENT_DIFF", "STANDARD_CONTEXT"]
EvidenceRef = Annotated[str, Field(pattern=r"^(?:REPORT|METRIC:[0-9]+|SAMPLE:[1-9][0-9]*|REPLAY)$")]
Text = Annotated[str, Field(min_length=1, max_length=1000)]


class GovernanceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: DecisionAction
    priority: IssuePriority
    rationale: Text
    evidenceRefs: list[EvidenceRef] = Field(min_length=1, max_length=10)
    sampleTaskId: RecordId | None = None
    hypothesis: Text | None = None
    expectedResult: Text | None = None
    missingEvidence: Text | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "GovernanceDecision":
        if self.action == "REPLAY":
            if self.sampleTaskId is None or not self.hypothesis or not self.expectedResult:
                raise ValueError("Replay requires a sample, hypothesis and expected result")
            if f"SAMPLE:{self.sampleTaskId}" not in self.evidenceRefs:
                raise ValueError("Replay must cite the selected sample")
        elif self.sampleTaskId is not None:
            raise ValueError("Only replay selects a sample")
        if self.action == "NEEDS_INPUT" and not self.missingEvidence:
            raise ValueError("Needs-input decisions must name the missing evidence")
        return self


class GovernanceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: AssessmentAction
    conclusion: Text
    nextStep: Text
    evidenceRefs: list[EvidenceRef] = Field(min_length=1, max_length=10)


class CreateGovernanceRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reportId: RecordId
    issueId: RecordId | None = None


class GovernanceIntervention(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["PAUSE", "RESUME", "CANCEL", "PRIORITIZE", "OVERRIDE"]
    revision: int = Field(strict=True, ge=0, le=2**31 - 1)
    priority: IssuePriority | None = None
    conclusion: Text | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "GovernanceIntervention":
        if (self.action == "PRIORITIZE") != (self.priority is not None):
            raise ValueError("Only a priority change requires a priority")
        if (self.action == "OVERRIDE") != (self.conclusion is not None):
            raise ValueError("Only an override requires a conclusion")
        return self


class GovernanceRunView(BaseModel):
    id: RecordId
    reportId: RecordId
    issueId: RecordId | None
    source: Literal["MANUAL", "SCHEDULED"]
    status: Literal["QUEUED", "RUNNING", "PAUSED", "SUCCEEDED", "FAILED", "CANCELLED"]
    createdAt: datetime
    updatedAt: datetime
    errorCode: str | None
    decision: GovernanceDecision | None = None
    assessment: GovernanceAssessment | None = None
    replay: dict | None = None


class GovernanceEventView(BaseModel):
    kind: str
    details: dict
    createdAt: datetime


class GovernanceRunDetail(GovernanceRunView):
    events: list[GovernanceEventView]
    evidence: dict
    controlRevision: int = 0
    paused: bool = False
    priority: IssuePriority | None = None
    override: str | None = None


class GovernanceIssueView(BaseModel):
    id: RecordId
    revision: int
    paused: bool
    title: str
    priority: IssuePriority
    affectedTaskCount: int
    status: str
    override: str | None
    run: GovernanceRunView
    effectiveRun: GovernanceRunView | None = None


class GovernanceOverview(BaseModel):
    enabled: bool
    latestRun: GovernanceRunView | None = None
    issues: list[GovernanceIssueView] = Field(default_factory=list)
    pageNo: int = 1
    hasMore: bool = False


def validate_evidence_refs(
    judgment: GovernanceDecision | GovernanceAssessment,
    available_refs: set[str],
    replayable_samples: set[int],
) -> None:
    if not set(judgment.evidenceRefs) <= available_refs:
        raise ValueError("The judgment cites unavailable evidence")
    if isinstance(judgment, GovernanceDecision) and judgment.action == "REPLAY":
        if judgment.sampleTaskId not in replayable_samples:
            raise ValueError("The selected sample is unavailable for replay")
    if isinstance(judgment, GovernanceAssessment) and "REPLAY" not in judgment.evidenceRefs:
        raise ValueError("The assessment must cite the replay")
