from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TargetType = Literal[
    "BACKEND",
    "WEB_PC",
    "APP_IOS",
    "APP_ANDROID",
    "APP_CROSS_PLATFORM",
    "GENERAL",
]


class ProjectReviewSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    trigger_on_mr: bool | None = Field(default=None, alias="triggerOnMr")
    trigger_on_push: bool | None = Field(default=None, alias="triggerOnPush")
    trigger_only_when_risk_matched: bool | None = Field(
        default=None,
        alias="triggerOnlyWhenRiskMatched",
    )
    auto_fix_preview_enabled: bool | None = Field(default=None, alias="autoFixPreviewEnabled")
    auto_fix_preview_severities: list[Literal["CRITICAL", "MAJOR", "MINOR"]] | None = Field(
        default=None,
        alias="autoFixPreviewSeverities",
    )
    push_branch_patterns: list[str] | None = Field(default=None, alias="pushBranchPatterns")
    push_min_changed_files: int | None = Field(default=None, alias="pushMinChangedFiles", ge=0)
    push_min_diff_bytes: int | None = Field(default=None, alias="pushMinDiffBytes", ge=0)
    push_min_commit_count: int | None = Field(default=None, alias="pushMinCommitCount", ge=0)
    push_max_changed_files: int | None = Field(default=None, alias="pushMaxChangedFiles", ge=-1)
    push_max_diff_bytes: int | None = Field(default=None, alias="pushMaxDiffBytes", ge=-1)
    push_debounce_seconds: int | None = Field(default=None, alias="pushDebounceSeconds", ge=0)


class ProjectTargetConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    template_code: str = Field(alias="templateCode", min_length=1, max_length=64)
    code_quality_profile_code: str | None = Field(
        alias="codeQualityProfileCode",
        default=None,
        max_length=64,
    )
    provider_code: str | None = Field(alias="providerCode", default=None, max_length=64)
    path_patterns: list[str] = Field(alias="pathPatterns", min_length=1)
    reminder_card_enabled: bool = Field(alias="reminderCardEnabled")


class ProjectAiReviewModelUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    review_key: str | None = Field(alias="reviewKey", default=None, max_length=64)
    provider_code: str = Field(alias="providerCode", min_length=1, max_length=64)
    model_name: str | None = Field(alias="modelName", default=None, max_length=128)
    display_name: str | None = Field(alias="displayName", default=None, max_length=128)
    enabled: bool = True
    sort_order: int = Field(alias="sortOrder", default=0)


class ProjectConfigurationUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    target_type: TargetType = Field(alias="targetType")
    target_config: ProjectTargetConfigUpdateRequest = Field(alias="targetConfig")
    ai_review_models: list[ProjectAiReviewModelUpdateRequest] = Field(alias="aiReviewModels")
    review_settings: ProjectReviewSettingsUpdateRequest = Field(alias="reviewSettings")
    webhook_ids: list[int] = Field(alias="webhookIds")
