from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
