from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NotificationWebhookCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=128)
    webhook_url: str = Field(alias="webhookUrl", min_length=1, max_length=1024)
    description: str | None = Field(default=None, max_length=512)
    enabled: bool = True


class NotificationWebhookUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=128)
    webhook_url: str | None = Field(default=None, alias="webhookUrl", max_length=1024)
    description: str | None = Field(default=None, max_length=512)
    enabled: bool | None = None


class ProjectNotificationWebhookBatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_ids: list[int] = Field(alias="projectIds", min_length=1)
    webhook_ids: list[int] = Field(default_factory=list, alias="webhookIds")
    mode: Literal["REPLACE", "ADD", "REMOVE"] = "REPLACE"