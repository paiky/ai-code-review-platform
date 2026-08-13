from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ProviderType = Literal[
    "OPENAI_CHAT_COMPATIBLE",
    "OPENAI_RESPONSES",
    "ANTHROPIC_MESSAGES",
]
ReasoningEffort = Literal["low", "medium", "high"]
ReviewType = Literal["AGENT", "STANDARD"]
ReviewModelConnectionProtocol = Literal[
    "ANTHROPIC_COMPATIBLE",
    "OPENAI_RESPONSES",
    "OPENAI_CHAT_COMPLETIONS",
    "OPENAI_CHAT_COMPATIBLE",
    "ANTHROPIC_MESSAGES",
]


class ReviewModelPresetVariant(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    protocol: str
    base_url: str | None = Field(alias="baseUrl")
    models: list[str]
    default_model: str | None = Field(alias="defaultModel")
    reasoning_efforts: list[ReasoningEffort] = Field(alias="reasoningEfforts")
    default_reasoning_effort: ReasoningEffort | None = Field(alias="defaultReasoningEffort")


class ReviewModelPreset(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    preset_code: str = Field(alias="presetCode")
    review_type: ReviewType = Field(alias="reviewType")
    vendor_code: str = Field(alias="vendorCode")
    vendor_name: str = Field(alias="vendorName")
    custom: bool
    variants: list[ReviewModelPresetVariant]


class CreateReviewModelConnectionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    review_type: ReviewType = Field(alias="reviewType")
    preset_code: str = Field(alias="presetCode", min_length=1, max_length=64)
    protocol: ReviewModelConnectionProtocol
    base_url: str = Field(alias="baseUrl", min_length=1, max_length=1024)
    model_name: str = Field(alias="model", min_length=1, max_length=128)
    reasoning_effort: ReasoningEffort | None = Field(
        default=None,
        alias="reasoningEffort",
    )
    api_key: str = Field(alias="apiKey", min_length=1, max_length=4096)
    tls_verify: bool = Field(default=True, alias="tlsVerify")

    @field_validator("review_type", "preset_code", "protocol", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("base_url", "model_name", "api_key", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_reasoning_effort(self) -> "CreateReviewModelConnectionRequest":
        supported = {"ANTHROPIC_COMPATIBLE", "OPENAI_RESPONSES"}
        if self.reasoning_effort is not None and self.protocol not in supported:
            raise ValueError(
                "reasoningEffort is only supported by ANTHROPIC_COMPATIBLE or OPENAI_RESPONSES"
            )
        return self


class CreateProviderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    provider_code: str = Field(alias="providerCode", pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    provider_name: str = Field(alias="providerName", min_length=1, max_length=128)
    provider_type: ProviderType = Field(alias="providerType")
    endpoint_url: str | None = Field(default=None, alias="endpointUrl", max_length=512)
    model_name: str | None = Field(default=None, alias="modelName", max_length=128)
    timeout_seconds: int | None = Field(default=None, alias="timeoutSeconds", ge=1, le=3600)
    reasoning_effort: ReasoningEffort | None = Field(default=None, alias="reasoningEffort")
    tls_verify: bool = Field(default=True, alias="tlsVerify")
    api_key: str | None = Field(default=None, alias="apiKey", max_length=1024)
    # Compatibility-only. Standard Providers are available by configuration completeness.
    enabled: bool = True

    @field_validator("provider_code", mode="before")
    @classmethod
    def normalize_provider_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("provider_name", mode="before")
    @classmethod
    def normalize_provider_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("endpoint_url", "model_name", "api_key", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_protocol_configuration(self) -> "CreateProviderRequest":
        if self.reasoning_effort is not None and self.provider_type != "OPENAI_RESPONSES":
            raise ValueError("reasoningEffort is only supported by OPENAI_RESPONSES")
        return self
