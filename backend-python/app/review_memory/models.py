from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMBLOB, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.json_utils import utc_now


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")
MEMORY_TEXT = Text().with_variant(MEDIUMTEXT(), "mysql")
MEMORY_BINARY = LargeBinary().with_variant(MEDIUMBLOB(), "mysql")
MEMORY_DATETIME = DateTime().with_variant(DATETIME(fsp=3), "mysql")
TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


class ReviewMemorySource(Base):
    __tablename__ = "review_memory_sources"
    __table_args__ = (
        UniqueConstraint("source_feedback_id", name="uk_review_memory_sources_feedback"),
        Index("idx_review_memory_sources_project_state_kind", "project_id", "state", "kind", "id"),
        Index("idx_review_memory_sources_project_sha", "project_id", "original_sha256"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    original_filename: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str | None] = mapped_column(String(100))
    original_bytes: Mapped[bytes | None] = mapped_column(MEMORY_BINARY, deferred=True)
    original_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    extracted_text: Mapped[str | None] = mapped_column(MEMORY_TEXT, deferred=True)
    parser_version: Mapped[str | None] = mapped_column(String(64))
    parse_warnings_json: Mapped[str | None] = mapped_column(Text)
    source_feedback_id: Mapped[int | None] = mapped_column(BigInteger)
    feedback_digest: Mapped[str | None] = mapped_column(CHAR(64))
    replacement_of_id: Mapped[int | None] = mapped_column(BigInteger)
    confirmed_by: Mapped[str | None] = mapped_column(String(128))
    confirmed_at: Mapped[datetime | None] = mapped_column(MEMORY_DATETIME)
    created_at: Mapped[datetime] = mapped_column(MEMORY_DATETIME, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(MEMORY_DATETIME, nullable=False, default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(MEMORY_DATETIME)


class ReviewMemoryEntry(Base):
    __tablename__ = "review_memory_entries"
    __table_args__ = (
        UniqueConstraint("source_id", "section_key", name="uk_review_memory_entries_section"),
        Index(
            "idx_review_memory_entries_source_state_scope",
            "source_id",
            "state",
            "load_mode",
            "target_type",
            "issue_type",
        ),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    section_key: Mapped[str] = mapped_column(String(128), nullable=False)
    heading: Mapped[str] = mapped_column(String(255), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(MEMORY_TEXT, nullable=False, deferred=True)
    target_type: Mapped[str | None] = mapped_column(String(32))
    issue_type: Mapped[str | None] = mapped_column(String(64))
    path_globs_json: Mapped[str | None] = mapped_column(Text)
    keywords_json: Mapped[str | None] = mapped_column(Text)
    load_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ON_DEMAND", server_default="ON_DEMAND"
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    content_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    validation_errors_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(MEMORY_DATETIME, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(MEMORY_DATETIME, nullable=False, default=utc_now)


class ReviewMemoryWriteback(Base):
    __tablename__ = "review_memory_writebacks"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uk_review_memory_writebacks_idempotency"),
        Index("idx_review_memory_writebacks_due", "state", "next_attempt_at", "id"),
        Index("idx_review_memory_writebacks_lease", "lease_until", "state"),
        Index("idx_review_memory_writebacks_feedback", "feedback_id", "id"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    feedback_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    feedback_digest: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    confirmation_json: Mapped[str] = mapped_column(MEMORY_TEXT, nullable=False, deferred=True)
    expected_source_version: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING", server_default="PENDING"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(MEMORY_DATETIME, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(MEMORY_DATETIME)
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    confirmed_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(MEMORY_DATETIME, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(MEMORY_DATETIME, nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(MEMORY_DATETIME)
