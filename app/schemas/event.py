from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class EventIn(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    ts: datetime
    source: str
    src_ip: str
    action: str
    object: Optional[str] = None
    trap_id: str | None = None
    user: Optional[str] = None
    host: Optional[str] = None
    raw: Any

class EventOut(BaseModel):
    event_id: UUID = Field(validation_alias="id")
    ts: datetime
    source: str
    rap_id: str | None = None
    src_ip: str
    action: str
    object: Optional[str] = None
    user: Optional[str] = None
    host: Optional[str] = None
    raw: Any

    class Config:
        from_attributes = True