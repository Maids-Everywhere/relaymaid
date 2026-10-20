from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from relaymaid.db.base import Base


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "event_id"],
            [
                "events.organization_id",
                "events.id",
            ],
            name="fk_outbox_messages_organization_event_events",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_outbox_messages_unpublished_created_at_id",
            "created_at",
            "id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )
    event_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
