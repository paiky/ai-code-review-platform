from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, UniqueConstraint
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
    push_min_changed_files: Mapped[int | None] = mapped_column(Integer)
    push_min_diff_bytes: Mapped[int | None] = mapped_column(Integer)
    push_min_commit_count: Mapped[int | None] = mapped_column(Integer)
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
    review_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mr_auto_review_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    dingtalk_notification_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_fix_preview_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_fix_preview_severities: Mapped[str | None] = mapped_column(Text)
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
    timeout_seconds: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    built_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class CodeQualityReviewResult(Base):
    __tablename__ = "code_quality_review_results"
    __table_args__ = (
        UniqueConstraint("task_id", "review_key", name="uk_code_quality_result_task_review_key"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    review_key: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    profile_code: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    display_name: Mapped[str | None] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    overall_level: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str | None] = mapped_column(String(1024))
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_json: Mapped[str] = mapped_column(Text, nullable=False)
    raw_output: Mapped[str | None] = mapped_column(Text)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(String(1024))
    requested_engine: Mapped[str] = mapped_column(String(32), nullable=False, default="STANDARD")
    effective_engine: Mapped[str] = mapped_column(String(32), nullable=False, default="STANDARD")
    agent_run_id: Mapped[int | None] = mapped_column(BigInteger)
    agent_summary_json: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[object | None] = mapped_column(DateTime)
    finished_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class CodeQualityReviewProgressEvent(Base):
    __tablename__ = "code_quality_review_progress_events"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    review_key: Mapped[str | None] = mapped_column(String(64))
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False, default="INFO")
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object | None] = mapped_column(DateTime)


class CodeQualityFixPreview(Base):
    __tablename__ = "code_quality_fix_previews"
    __table_args__ = (
        UniqueConstraint("task_id", "review_key", "finding_index", name="uk_code_quality_fix_preview_task_review_finding"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    review_key: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    finding_index: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    summary: Mapped[str | None] = mapped_column(String(1024))
    patch_text: Mapped[str | None] = mapped_column(Text)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class CodeQualityFindingRefinement(Base):
    __tablename__ = "code_quality_finding_refinements"
    __table_args__ = (
        UniqueConstraint("task_id", "review_key", "finding_index", name="uk_code_quality_refinement_task_review_finding"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    review_key: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    finding_index: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String(128))
    finding_id: Mapped[str | None] = mapped_column(String(128))
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_reason: Mapped[str | None] = mapped_column(String(255))
    trigger_conditions_json: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_plan_json: Mapped[str | None] = mapped_column(Text)
    evidence_summary_json: Mapped[str | None] = mapped_column(Text)
    missing_context_json: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(String(1024))
    started_at: Mapped[object | None] = mapped_column(DateTime)
    finished_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class CodeQualitySchedulerJob(Base):
    __tablename__ = "code_quality_scheduler_jobs"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    review_key: Mapped[str | None] = mapped_column(String(64))
    project_id: Mapped[int | None] = mapped_column(BigInteger)
    finding_index: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    file_path: Mapped[str | None] = mapped_column(String(512))
    error_message: Mapped[str | None] = mapped_column(String(1024))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[object | None] = mapped_column(DateTime)
    heartbeat_at: Mapped[object | None] = mapped_column(DateTime)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    cancel_requested_at: Mapped[object | None] = mapped_column(DateTime)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    queued_at: Mapped[object | None] = mapped_column(DateTime)
    started_at: Mapped[object | None] = mapped_column(DateTime)
    finished_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class CodeQualityPushReviewGateDecision(Base):
    __tablename__ = "code_quality_push_review_gate_decisions"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    branch_name: Mapped[str | None] = mapped_column(String(255))
    profile_code: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    ai_review_scheduled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_summary: Mapped[str] = mapped_column(String(512), nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    matched_rules_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)
