from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from relaymaid.db.base import Base


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_webhook_endpoints_organization_id_id",
        ),
        Index(
            "ix_webhook_endpoints_organization_id",
            "organization_id",
        ),
        CheckConstraint(
            "retry_limit BETWEEN 0 AND 10",
            name="ck_webhook_endpoints_retry_limit_range",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    public_id: Mapped[UUID] = mapped_column(
        nullable=False,
        unique=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    secret_ciphertext: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    destination_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(
        nullable=False,
        default=true(),
    )
    retry_limit: Mapped[int] = mapped_column(
        nullable=False,
        default=text("3"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
