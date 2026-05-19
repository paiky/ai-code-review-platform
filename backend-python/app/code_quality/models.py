from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class CodeQualityReviewProfile(Base):
    __tablename__ = "code_quality_review_profiles"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    profile_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="CODEX_CLI")
    provider_code: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    trigger_on_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trigger_on_mr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trigger_on_push: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    severity_threshold: Mapped[str] = mapped_column(String(32), nullable=False, default="MAJOR")
    block_on_severities: Mapped[str] = mapped_column(Text, nullable=False)
    enabled_categories: Mapped[str] = mapped_column(Text, nullable=False)
    ignored_paths: Mapped[str] = mapped_column(Text, nullable=False)
    push_branch_patterns: Mapped[str] = mapped_column(Text, nullable=False)
    push_max_changed_files: Mapped[int | None] = mapped_column(Integer)
    push_max_diff_bytes: Mapped[int | None] = mapped_column(Integer)
    push_debounce_seconds: Mapped[int | None] = mapped_column(Integer)
    trigger_only_when_risk_matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    codex_prompt: Mapped[str | None] = mapped_column(Text)
    openai_instructions: Mapped[str | None] = mapped_column(Text)
    review_instructions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ENABLED")
    description: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class CodeQualityReviewSettings(Base):
    __tablename__ = "code_quality_review_settings"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    mr_auto_review_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    dingtalk_notification_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    review_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="DEEPSEEK")
    default_provider_code: Mapped[str] = mapped_column(String(64), nullable=False, default="DEEPSEEK")
    openai_api_key: Mapped[str | None] = mapped_column(String(1024))
    anthropic_api_key: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class CodeQualityModelProvider(Base):
    __tablename__ = "code_quality_model_providers"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    provider_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(String(512))
    model_name: Mapped[str | None] = mapped_column(String(128))
    api_key: Mapped[str | None] = mapped_column(String(1024))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    built_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class CodeQualityReviewResult(Base):
    __tablename__ = "code_quality_review_results"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    profile_code: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    overall_level: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str | None] = mapped_column(String(1024))
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_json: Mapped[str] = mapped_column(Text, nullable=False)
    raw_output: Mapped[str | None] = mapped_column(Text)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(String(1024))
    started_at: Mapped[object | None] = mapped_column(DateTime)
    finished_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class CodeQualityReviewProgressEvent(Base):
    __tablename__ = "code_quality_review_progress_events"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False, default="INFO")
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object | None] = mapped_column(DateTime)
