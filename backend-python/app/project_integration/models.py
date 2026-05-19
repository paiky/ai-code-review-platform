from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    git_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    git_project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    repository_url: Mapped[str | None] = mapped_column(String(512))
    default_template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    default_code_quality_profile_code: Mapped[str | None] = mapped_column(String(64))
    default_code_quality_provider_code: Mapped[str | None] = mapped_column(String(64))
    dingtalk_webhook_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class GitLabMergeRequestEvent(Base):
    __tablename__ = "gitlab_mr_webhook_events"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    git_project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_name: Mapped[str] = mapped_column(String(128), nullable=False)
    mr_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_action: Mapped[str | None] = mapped_column(String(64))
    event_time: Mapped[object | None] = mapped_column(DateTime)
    source_branch: Mapped[str | None] = mapped_column(String(255))
    target_branch: Mapped[str | None] = mapped_column(String(255))
    author_name: Mapped[str | None] = mapped_column(String(128))
    author_username: Mapped[str | None] = mapped_column(String(128))
    changed_files_summary: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class GitLabPushEvent(Base):
    __tablename__ = "gitlab_push_webhook_events"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    git_project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_name: Mapped[str] = mapped_column(String(128), nullable=False)
    ref: Mapped[str | None] = mapped_column(String(255))
    branch_name: Mapped[str | None] = mapped_column(String(255))
    before_sha: Mapped[str | None] = mapped_column(String(128))
    after_sha: Mapped[str] = mapped_column(String(128), nullable=False)
    event_time: Mapped[object | None] = mapped_column(DateTime)
    author_name: Mapped[str | None] = mapped_column(String(128))
    author_username: Mapped[str | None] = mapped_column(String(128))
    changed_files_summary: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)
