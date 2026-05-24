from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    group_id: Mapped[int | None] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    git_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    git_project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    repository_url: Mapped[str | None] = mapped_column(String(512))
    supported_target_types: Mapped[str | None] = mapped_column(Text)
    detected_target_types: Mapped[str | None] = mapped_column(Text)
    target_detection_json: Mapped[str | None] = mapped_column(Text)
    default_template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    default_code_quality_profile_code: Mapped[str | None] = mapped_column(String(64))
    default_code_quality_provider_code: Mapped[str | None] = mapped_column(String(64))
    dingtalk_webhook_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class ProjectGroup(Base):
    __tablename__ = "project_groups"
    __table_args__ = (
        UniqueConstraint("group_code", name="uk_project_group_code"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    group_name: Mapped[str] = mapped_column(String(128), nullable=False)
    group_code: Mapped[str | None] = mapped_column(String(64))
    default_provider_code: Mapped[str | None] = mapped_column(String(64))
    push_branch_patterns: Mapped[str | None] = mapped_column(Text)
    push_min_changed_files: Mapped[int | None] = mapped_column(Integer)
    push_min_diff_bytes: Mapped[int | None] = mapped_column(Integer)
    push_min_commit_count: Mapped[int | None] = mapped_column(Integer)
    push_max_changed_files: Mapped[int | None] = mapped_column(Integer)
    push_max_diff_bytes: Mapped[int | None] = mapped_column(Integer)
    push_debounce_seconds: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ENABLED")
    description: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class ProjectTargetConfig(Base):
    __tablename__ = "project_target_configs"
    __table_args__ = (
        UniqueConstraint("project_id", "target_type", name="uk_project_target_config"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    code_quality_profile_code: Mapped[str | None] = mapped_column(String(64))
    provider_code: Mapped[str | None] = mapped_column(String(64))
    path_patterns: Mapped[str] = mapped_column(Text, nullable=False)
    reminder_card_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
