from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(BigInteger)
    review_key: Mapped[str | None] = mapped_column(String(64))
    finding_id: Mapped[str | None] = mapped_column(String(128))
    fingerprint: Mapped[str | None] = mapped_column(String(128))
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    profile: Mapped[str | None] = mapped_column(String(64))
    risk_type: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[str | None] = mapped_column(String(32))
    context_status: Mapped[str | None] = mapped_column(String(32))
    verdict: Mapped[str] = mapped_column(String(64), nullable=False)
    human_comment: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    item_snapshot_json: Mapped[str | None] = mapped_column(Text)
    rule_gap_attribution_type: Mapped[str | None] = mapped_column(String(64))
    rule_gap_summary_json: Mapped[str | None] = mapped_column(Text)
    rule_gap_attribution_comment: Mapped[str | None] = mapped_column(Text)
    rule_gap_attributed_by: Mapped[str | None] = mapped_column(String(128))
    rule_gap_attributed_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sample_set_name: Mapped[str | None] = mapped_column(String(255))
    sample_set_json: Mapped[str | None] = mapped_column(Text)
    project_id: Mapped[int | None] = mapped_column(BigInteger)
    provider: Mapped[str | None] = mapped_column(String(64))
    profile: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_hash: Mapped[str | None] = mapped_column(String(128))
    context_pack_version: Mapped[str | None] = mapped_column(String(64))
    retriever_version: Mapped[str | None] = mapped_column(String(64))
    rule_gap_version: Mapped[str | None] = mapped_column(String(64))
    baseline_json: Mapped[str | None] = mapped_column(Text)
    candidate_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_summary_json: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[object | None] = mapped_column(DateTime)
    finished_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class EvaluationRunItem(Base):
    __tablename__ = "evaluation_run_items"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    case_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[int | None] = mapped_column(BigInteger)
    review_key: Mapped[str | None] = mapped_column(String(64))
    fingerprint: Mapped[str | None] = mapped_column(String(128))
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    profile: Mapped[str | None] = mapped_column(String(64))
    risk_type: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[str | None] = mapped_column(String(32))
    context_status: Mapped[str | None] = mapped_column(String(32))
    verdict: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    baseline_summary_json: Mapped[str | None] = mapped_column(Text)
    candidate_summary_json: Mapped[str | None] = mapped_column(Text)
    result_summary_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)
