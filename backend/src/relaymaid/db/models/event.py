from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from relaymaid.db.base import Base
from relaymaid.domain import EventStatus


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "endpoint_id"],
            [
                "webhook_endpoints.organization_id",
                "webhook_endpoints.id",
            ],
            name="fk_events_organization_endpoint_webhook_endpoints",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_events_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "endpoint_id",
            "external_event_id",
            name="uq_events_organization_endpoint_external_event",
        ),
        Index(
            "ix_events_organization_received_at_id",
            "organization_id",
            "received_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )
    endpoint_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )
    external_event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    payload_raw: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[EventStatus] = mapped_column(
        Enum(
            EventStatus,
            name="event_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=text("'pending'"),
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
