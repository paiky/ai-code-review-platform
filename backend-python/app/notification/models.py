from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
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
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ENABLED")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[object | None] = mapped_column(DateTime)
    updated_at: Mapped[object | None] = mapped_column(DateTime)
