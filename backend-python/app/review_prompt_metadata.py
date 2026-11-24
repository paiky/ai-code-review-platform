from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.agent_review_spike.budgets import AGENT_BUDGET_LIMITS
from app.agent_review_spike.prompting import agent_platform_instructions_v1
from app.code_quality.prompt import STANDARD_PLATFORM_INSTRUCTIONS_V1


REVIEW_PLATFORM_PROMPT = "REVIEW_PLATFORM_PROMPT"


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
