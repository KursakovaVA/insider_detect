import uuid
from datetime import datetime
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db import Base

class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    trap_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="core")

    source: Mapped[str] = mapped_column(String(64), nullable=False)
    src_ip: Mapped[str] = mapped_column(String(64), nullable=False)

    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object: Mapped[str | None] = mapped_column(String(256), nullable=True)

    user: Mapped[str | None] = mapped_column(String(128), nullable=True)
    host: Mapped[str | None] = mapped_column(String(128), nullable=True)

    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)


