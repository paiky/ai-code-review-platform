from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator

from app.agent_review_spike.budgets import AGENT_BUDGET_LIMITS
from app.review_prompt_metadata import (
    MAX_REVIEW_INPUT_BYTES,
    REVIEW_PLATFORM_PROMPT,
    PlatformPromptMarker,
    ReviewInputSource,
    ReviewProfileInput,
)


AgentRuntimeProtocol = Literal[
    "OPENAI_RESPONSES",
    "OPENAI_CHAT_COMPLETIONS",
    "ANTHROPIC_MESSAGES",
]
ReasoningEffort = Literal["low", "medium", "high"]

AGENT_CONVERSATION_INPUT = "AGENT_CONVERSATION_INPUT"
AGENT_CONVERSATION_TURN = "AGENT_CONVERSATION_TURN"
AGENT_CONVERSATION_PHASES = (
    AGENT_CONVERSATION_INPUT, AGENT_CONVERSATION_TURN, REVIEW_PLATFORM_PROMPT
)
AgentConversationSummarySource = Literal["OPENAI_RESPONSES_REASONING_SUMMARY"]
AgentConversationSummaryKind = Literal[
    "CHECK_CALL_SITES", "READ_SOURCE", "INSPECT_DIFF", "PREPARE_SUBMISSION"
]
OPENAI_RESPONSES_SUMMARY_SOURCE: AgentConversationSummarySource = "OPENAI_RESPONSES_REASONING_SUMMARY"
_MAX_CONVERSATION_TURNS = AGENT_BUDGET_LIMITS["maxTurns"]["max"]
_MAX_CONVERSATION_TOOL_SEQUENCES = AGENT_BUDGET_LIMITS["maxToolCalls"]["max"]
_MAX_CONVERSATION_SOURCES = 8
_TOKEN_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


class AgentConversationInputEvent(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    phase: Literal["AGENT_CONVERSATION_INPUT"]
    schemaVersion: Literal[1]
    protocol: Literal[
        "OPENAI_RESPONSES",
        "OPENAI_CHAT_COMPLETIONS",
        "ANTHROPIC_MESSAGES",
        "ANTHROPIC_COMPATIBLE",
    ]
    diffMode: Literal["INLINE", "TOOL_PAGED"]
    changedFileCount: int | None = Field(default=None, ge=0, le=10_000)
    requestBytes: int | None = Field(default=None, ge=0, le=MAX_REVIEW_INPUT_BYTES)
    diffBytes: int | None = Field(default=None, ge=0, le=MAX_REVIEW_INPUT_BYTES)
    profile: ReviewProfileInput | None = None
    sourceSummaries: list[ReviewInputSource] | None = Field(
        default=None, max_length=_MAX_CONVERSATION_SOURCES
    )
    truncated: bool | None = None


class AgentConversationTurnEvent(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    phase: Literal["AGENT_CONVERSATION_TURN"]
    schemaVersion: Literal[1]
    turn: int = Field(ge=1, le=_MAX_CONVERSATION_TURNS)
    toolSequences: list[Annotated[int, Field(ge=1, le=_MAX_CONVERSATION_TOOL_SEQUENCES)]] | None = Field(
        default=None, max_length=_MAX_CONVERSATION_TOOL_SEQUENCES
    )
    modelRequestMs: int | None = Field(
        default=None, ge=0, le=AGENT_BUDGET_LIMITS["timeoutSeconds"]["max"] * 1_000
    )
    usage: dict[str, int] | None = None
    evidenceStatus: Literal["MEASURED", "UNAVAILABLE"] | None = None
    newEvidenceCount: int | None = Field(default=None, ge=0, le=1_000_000)
    consecutiveNoNewEvidenceTurns: int | None = Field(default=None, ge=0, le=_MAX_CONVERSATION_TURNS)
    summarySource: AgentConversationSummarySource | None = None
    summaryKind: AgentConversationSummaryKind | None = None
    truncated: bool | None = None

    @field_validator("usage", mode="before")
    @classmethod
    def filter_usage(cls, value: object) -> dict[str, int] | None:
        if not isinstance(value, dict):
            return None
        counts = {
            key: value[key]
            for key in _TOKEN_USAGE_FIELDS
            if type(value.get(key)) is int and 0 <= value[key] <= 10_000_000_000
        }
        return counts or None

    @field_validator("evidenceStatus", mode="before")
    @classmethod
    def filter_evidence_status(cls, value: object) -> object:
        return value if value in ("MEASURED", "UNAVAILABLE") else None

    @field_validator("summarySource", mode="before")
    @classmethod
    def filter_summary_source(cls, value: object) -> object:
        return value if value == OPENAI_RESPONSES_SUMMARY_SOURCE else None

    @field_validator("summaryKind", mode="before")
    @classmethod
    def filter_summary_kind(cls, value: object) -> object:
        return value if value in get_args(AgentConversationSummaryKind) else None

    @model_validator(mode="after")
    def normalize_optional_fields(self) -> "AgentConversationTurnEvent":
        if self.evidenceStatus != "MEASURED":
            self.newEvidenceCount = None
            self.consecutiveNoNewEvidenceTurns = None
        elif (
            self.consecutiveNoNewEvidenceTurns is not None
            and self.consecutiveNoNewEvidenceTurns > self.turn
        ):
            self.consecutiveNoNewEvidenceTurns = None
        if self.summarySource is None or self.summaryKind is None:
            self.summarySource = None
            self.summaryKind = None
        return self


AgentConversationEvent = AgentConversationInputEvent | AgentConversationTurnEvent | PlatformPromptMarker
_CONVERSATION_EVENT_ADAPTER = TypeAdapter(Annotated[AgentConversationEvent, Field(discriminator="phase")])


def parse_agent_conversation_events(value: Any) -> list[AgentConversationEvent]:
    if not isinstance(value, list):
        return []
    events: list[AgentConversationEvent] = []
    for item in value[: _MAX_CONVERSATION_TURNS + 2]:
        if not isinstance(item, dict) or type(item.get("schemaVersion")) is not int:
            continue
        if item["schemaVersion"] != 1:
            continue
        event = dict(item)
        for field, limit in (
            ("sourceSummaries", _MAX_CONVERSATION_SOURCES),
            ("toolSequences", _MAX_CONVERSATION_TOOL_SEQUENCES),
        ):
            values = item.get(field)
            if isinstance(values, list) and len(values) > limit:
                event[field] = values[:limit]
                event["truncated"] = True
        try:
            events.append(_CONVERSATION_EVENT_ADAPTER.validate_python(event))
        except ValidationError:
            continue
    return events


class CreateAgentRuntimeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    runtime_code: str = Field(
        alias="runtimeCode",
        pattern=r"^[A-Z][A-Z0-9_]{0,39}$",
    )
    display_name: str = Field(alias="displayName", min_length=1, max_length=64)
    protocol: AgentRuntimeProtocol
    base_url: str = Field(alias="baseUrl", min_length=1, max_length=1024)
    model_name: str = Field(alias="model", min_length=1, max_length=128)
    reasoning_effort: ReasoningEffort | None = Field(
        default=None,
        alias="reasoningEffort",
    )
    tls_verify: bool = Field(default=True, alias="tlsVerify")
    api_key: str | None = Field(default=None, alias="apiKey", max_length=4096)
    enabled: bool = False

    @field_validator("runtime_code", "protocol", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("display_name", "base_url", "model_name", "api_key", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_protocol_fields(self) -> "CreateAgentRuntimeRequest":
        if self.protocol == "OPENAI_RESPONSES" and self.reasoning_effort is None:
            self.reasoning_effort = "high"
        if self.protocol != "OPENAI_RESPONSES" and self.reasoning_effort is not None:
            raise ValueError("reasoningEffort is only supported by OPENAI_RESPONSES")
        if self.enabled and not self.api_key:
            raise ValueError("apiKey is required when enabled is true")
        return self


class UpdateAgentRuntimeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    display_name: str | None = Field(default=None, alias="displayName", min_length=1, max_length=64)
    base_url: str | None = Field(default=None, alias="baseUrl", min_length=1, max_length=1024)
    model_name: str | None = Field(default=None, alias="model", min_length=1, max_length=128)
    reasoning_effort: ReasoningEffort | None = Field(default=None, alias="reasoningEffort")
    tls_verify: bool | None = Field(default=None, alias="tlsVerify")
    api_key: str | None = Field(default=None, alias="apiKey", max_length=4096)
    clear_api_key: bool = Field(default=False, alias="clearApiKey")
    enabled: bool | None = None

    @field_validator("display_name", "base_url", "model_name", "api_key", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_key_mutation(self) -> "UpdateAgentRuntimeRequest":
        if self.clear_api_key and self.api_key is not None:
            raise ValueError("apiKey and clearApiKey cannot be submitted together")
        required_when_submitted = {
            "display_name": self.display_name,
            "base_url": self.base_url,
            "model_name": self.model_name,
            "reasoning_effort": self.reasoning_effort,
            "tls_verify": self.tls_verify,
            "enabled": self.enabled,
        }
        for field_name, value in required_when_submitted.items():
            if field_name in self.model_fields_set and value is None:
                alias = type(self).model_fields[field_name].alias or field_name
                raise ValueError(f"{alias} cannot be null")
        return self


class TestAgentRuntimeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    base_url: str | None = Field(default=None, alias="baseUrl", min_length=1, max_length=1024)
    model_name: str | None = Field(default=None, alias="model", min_length=1, max_length=128)
    reasoning_effort: ReasoningEffort | None = Field(default=None, alias="reasoningEffort")
    tls_verify: bool | None = Field(default=None, alias="tlsVerify")
    api_key: str | None = Field(default=None, alias="apiKey", max_length=4096)

    @field_validator("base_url", "model_name", "api_key", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None
