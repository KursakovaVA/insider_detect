import uuid
from datetime import datetime
from sqlalchemy import DateTime, String, Float, Integer
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

class Profile(Base):
    __tablename__ = "profiles"

    trap_id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default="core")
    src_ip: Mapped[str] = mapped_column(String(128), primary_key=True)

    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    ts_opened: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    ts_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    trap_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="core")

    src_ip: Mapped[str] = mapped_column(String(128), nullable=False)

    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")

    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    dedup_key: Mapped[str] = mapped_column(String(256), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
