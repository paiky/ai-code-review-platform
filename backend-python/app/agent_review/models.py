from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class AgentReviewSettings(Base):
    __tablename__ = "code_quality_agent_settings"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    api_key_fingerprint: Mapped[str | None] = mapped_column(String(32))
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


class AgentReviewRun(Base):
    __tablename__ = "agent_review_runs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uk_agent_review_run_idempotency"),)

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    review_key: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduler_job_id: Mapped[int | None] = mapped_column(BigInteger)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_engine: Mapped[str] = mapped_column(String(32), nullable=False, default="AGENT")
    effective_engine: Mapped[str | None] = mapped_column(String(32))
    runner_version: Mapped[str] = mapped_column(String(64), nullable=False, default="agent-worker-v1")
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
    input_json: Mapped[str | None] = mapped_column(Text)
    completion_context_json: Mapped[str | None] = mapped_column(Text)
    comparison_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(String(1024))
    heartbeat_at: Mapped[object | None] = mapped_column(DateTime)
    started_at: Mapped[object | None] = mapped_column(DateTime)
    finished_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)
