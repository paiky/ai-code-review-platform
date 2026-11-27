from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.agent_review_spike.budgets import AGENT_BUDGET_LIMITS
from app.agent_review_spike.prompting import agent_platform_instructions_v1
from app.code_quality.prompt import STANDARD_PLATFORM_INSTRUCTIONS_V1


REVIEW_PLATFORM_PROMPT = "REVIEW_PLATFORM_PROMPT"
MAX_REVIEW_INPUT_BYTES = 10 * 1024 * 1024


class ReviewInputSource(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    source: Literal[
        "PLATFORM_INSTRUCTIONS", "PROFILE", "PROJECT_POLICY", "PREFLIGHT", "MEMORY",
        "BASELINE_CONTEXT", "CHANGED_FILES", "DIFF", "CONTEXT_PACK",
    ]
    count: int | None = Field(default=None, ge=0, le=10_000)
    bytes: int | None = Field(default=None, ge=0, le=MAX_REVIEW_INPUT_BYTES)
    truncated: bool | None = None


class ReviewProfileInput(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    code: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    bytes: int | None = Field(default=None, ge=0, le=MAX_REVIEW_INPUT_BYTES)


def review_profile_input(code: str | None, instructions: str | None) -> ReviewProfileInput | None:
    if not code:
        return None
    encoded = instructions.strip().encode("utf-8") if instructions is not None else None
    try:
        return ReviewProfileInput(
            code=code,
            sha256=hashlib.sha256(encoded).hexdigest() if encoded is not None else None,
            bytes=len(encoded) if encoded is not None else None,
        )
    except ValidationError:
        return None


class PlatformPromptMarker(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    phase: Literal["REVIEW_PLATFORM_PROMPT"] = REVIEW_PLATFORM_PROMPT
    schemaVersion: Literal[1] = 1
    templateId: Literal["STANDARD_SYSTEM_V1", "AGENT_SYSTEM_V1"]
    source: Literal["STANDARD_HTTP", "AGENT_HTTP", "CLAUDE_CLI_APPEND"]
    protocol: Literal[
        "OPENAI_RESPONSES", "OPENAI_CHAT_COMPLETIONS", "ANTHROPIC_MESSAGES",
        "ANTHROPIC_COMPATIBLE",
    ]
    submitByTurn: int | None = Field(
        default=None,
        ge=AGENT_BUDGET_LIMITS["submitByTurn"]["min"],
        le=AGENT_BUDGET_LIMITS["submitByTurn"]["max"],
    )
    effectiveEngine: Literal["STANDARD", "STANDARD_FALLBACK"] | None = None
    runId: int | None = Field(default=None, gt=0)
    claimAttempt: int | None = Field(default=None, gt=0)
    profile: ReviewProfileInput | None = None
    sourceSummaries: list[ReviewInputSource] | None = Field(default=None, max_length=8)
    requestBytes: int | None = Field(default=None, ge=0, le=MAX_REVIEW_INPUT_BYTES)

    @model_validator(mode="after")
    def validate_source(self) -> PlatformPromptMarker:
        if self.source == "STANDARD_HTTP":
            if (
                self.templateId != "STANDARD_SYSTEM_V1"
                or self.effectiveEngine is None
                or self.submitByTurn is not None
                or self.claimAttempt is not None
                or self.protocol == "ANTHROPIC_COMPATIBLE"
                or (self.effectiveEngine == "STANDARD" and self.runId is not None)
            ):
                raise ValueError("Invalid Standard prompt marker")
        elif (
            self.templateId != "AGENT_SYSTEM_V1"
            or self.submitByTurn is None
            or self.effectiveEngine is not None
            or (self.source == "CLAUDE_CLI_APPEND") != (self.protocol == "ANTHROPIC_COMPATIBLE")
            or (self.runId is None) != (self.claimAttempt is None)
        ):
            raise ValueError("Invalid Agent prompt marker")
        return self

    def detail(self) -> dict[str, Any]:
        return self.model_dump(exclude={"phase"}, exclude_none=True)


def public_platform_prompt_detail(raw_detail: str | None) -> str | None:
    try:
        value = json.loads(raw_detail or "null")
        if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int:
            return None
        marker = PlatformPromptMarker.model_validate(value)
    except (ValidationError, ValueError, RecursionError):
        return None
    if marker.templateId == "STANDARD_SYSTEM_V1":
        instructions = STANDARD_PLATFORM_INSTRUCTIONS_V1
    else:
        if marker.runId is None or marker.submitByTurn is None:
            return None
        instructions = agent_platform_instructions_v1(marker.submitByTurn)
    return json.dumps(
        {**marker.detail(), "platformInstructions": instructions},
        ensure_ascii=False,
        separators=(",", ":"),
    )
