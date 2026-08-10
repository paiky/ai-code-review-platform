from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ProviderType = Literal[
    "OPENAI_CHAT_COMPATIBLE",
    "OPENAI_RESPONSES",
    "ANTHROPIC_MESSAGES",
]


class CreateProviderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    provider_code: str = Field(alias="providerCode", pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    provider_name: str = Field(alias="providerName", min_length=1, max_length=128)
    provider_type: ProviderType = Field(alias="providerType")
    endpoint_url: str | None = Field(default=None, alias="endpointUrl", max_length=512)
    model_name: str | None = Field(default=None, alias="modelName", max_length=128)
    timeout_seconds: int | None = Field(default=None, alias="timeoutSeconds", ge=1, le=3600)
    api_key: str | None = Field(default=None, alias="apiKey", max_length=1024)
    enabled: bool = False

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
    def validate_enabled_configuration(self) -> "CreateProviderRequest":
        if self.enabled and not self.endpoint_url:
            raise ValueError("endpointUrl is required when enabled is true")
        if self.enabled and not self.model_name:
            raise ValueError("modelName is required when enabled is true")
        if self.enabled and not self.api_key:
            raise ValueError("apiKey is required when enabled is true")
        return self
