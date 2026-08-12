from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AgentRuntimeProtocol = Literal[
    "OPENAI_RESPONSES",
    "OPENAI_CHAT_COMPLETIONS",
    "ANTHROPIC_MESSAGES",
]
ReasoningEffort = Literal["low", "medium", "high"]


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
