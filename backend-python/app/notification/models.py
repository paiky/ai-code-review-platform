from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class NotificationWebhook(Base):
    __tablename__ = "notification_webhooks"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    project_group_id: Mapped[int | None] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="DINGTALK")
    webhook_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret_ref: Mapped[str | None] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(String(512))
    last_test_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNTESTED")
    last_test_at: Mapped[object | None] = mapped_column(DateTime)
    last_test_message: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ENABLED")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)


class ProjectNotificationWebhook(Base):
    __tablename__ = "project_notification_webhooks"
    __table_args__ = (
        UniqueConstraint("project_id", "webhook_id", name="uk_project_notification_webhook"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    webhook_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)
