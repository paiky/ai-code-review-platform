from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")
LARGE_JSON_TEXT_TYPE = Text().with_variant(LONGTEXT(), "mysql")


class AgentReviewSettings(Base):
    __tablename__ = "code_quality_agent_settings"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    api_key_fingerprint: Mapped[str | None] = mapped_column(String(32))
    runtime_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="CLAUDE_CODE_DEEPSEEK"
    )
    selected_runtime_code: Mapped[str] = mapped_column(
        String(40), nullable=False, default="CLAUDE_CODE_DEEPSEEK"
    )
    custom_display_name: Mapped[str | None] = mapped_column(String(64))
    custom_base_url: Mapped[str | None] = mapped_column(String(1024))
    custom_model: Mapped[str | None] = mapped_column(String(128))
    custom_reasoning_effort: Mapped[str | None] = mapped_column(String(16))
    custom_tls_verify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    custom_api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    custom_api_key_fingerprint: Mapped[str | None] = mapped_column(String(32))
    budget_config_json: Mapped[str | None] = mapped_column(Text)
    worker_id: Mapped[str | None] = mapped_column(String(128))
    worker_version: Mapped[str | None] = mapped_column(String(64))
    cli_version: Mapped[str | None] = mapped_column(String(64))
    last_worker_heartbeat_at: Mapped[object | None] = mapped_column(DateTime)
    test_request_id: Mapped[str | None] = mapped_column(String(128))
    test_status: Mapped[str | None] = mapped_column(String(32))
    test_message: Mapped[str | None] = mapped_column(String(512))
    test_duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    test_started_at: Mapped[object | None] = mapped_column(DateTime)
    test_finished_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class AgentReviewRuntime(Base):
    __tablename__ = "code_quality_agent_runtimes"
    __table_args__ = (
        Index(
            "idx_code_quality_agent_runtimes_enabled_sort",
            "enabled",
            "sort_order",
            "runtime_code",
        ),
    )

    runtime_code: Mapped[str] = mapped_column(String(40), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    runner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(1024))
    model_name: Mapped[str | None] = mapped_column(String(128))
    reasoning_effort: Mapped[str | None] = mapped_column(String(16))
    tls_verify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    built_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    api_key_fingerprint: Mapped[str | None] = mapped_column(String(32))
    test_request_id: Mapped[str | None] = mapped_column(String(128))
    test_status: Mapped[str | None] = mapped_column(String(32))
    test_message: Mapped[str | None] = mapped_column(String(512))
    test_duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    test_started_at: Mapped[object | None] = mapped_column(DateTime)
    test_finished_at: Mapped[object | None] = mapped_column(DateTime)
    test_runtime_snapshot_json: Mapped[str | None] = mapped_column(Text)
    test_api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class AgentReviewWorker(Base):
    __tablename__ = "code_quality_agent_workers"
    __table_args__ = (
        Index("idx_code_quality_agent_workers_heartbeat", "last_heartbeat_at"),
    )

    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    worker_version: Mapped[str | None] = mapped_column(String(64))
    cli_version: Mapped[str | None] = mapped_column(String(64))
    capabilities_json: Mapped[str | None] = mapped_column(Text)
    responses_runner_version: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="IDLE")
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active_job_id: Mapped[int | None] = mapped_column(BigInteger)
    active_run_id: Mapped[int | None] = mapped_column(BigInteger)
    started_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    last_heartbeat_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime, nullable=False)


class AgentReviewRun(Base):
    __tablename__ = "agent_review_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uk_agent_review_run_idempotency"),
        Index(
            "idx_agent_review_runs_cc_status_updated",
            "status",
            "updated_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    review_key: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduler_job_id: Mapped[int | None] = mapped_column(BigInteger)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_engine: Mapped[str] = mapped_column(String(32), nullable=False, default="AGENT")
    effective_engine: Mapped[str | None] = mapped_column(String(32))
    runner_version: Mapped[str] = mapped_column(String(64), nullable=False, default="agent-worker-v1")
    runner_type: Mapped[str] = mapped_column(String(32), nullable=False, default="CLAUDE_CODE")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="DEEPSEEK")
    cli_version: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="deepseek-v4-pro[1m]")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    session_id: Mapped[str | None] = mapped_column(String(128))
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_bytes_returned: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    diff_bytes_returned: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    usage_json: Mapped[str | None] = mapped_column(Text)
    tool_summary_json: Mapped[str | None] = mapped_column(Text)
    input_json: Mapped[str | None] = mapped_column(LARGE_JSON_TEXT_TYPE)
    completion_context_json: Mapped[str | None] = mapped_column(LARGE_JSON_TEXT_TYPE)
    comparison_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(String(1024))
    heartbeat_at: Mapped[object | None] = mapped_column(DateTime)
    started_at: Mapped[object | None] = mapped_column(DateTime)
    finished_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)
