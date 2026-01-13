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
    #delta: Optional[float] = None
    #matched_rules: Optional[list[dict[str, Any]]] = None

    class Config:
        from_attributes = True

class ProfileOut(BaseModel):
    trap_id: str
    src_ip: str
    risk_score: float
    last_seen: Optional[datetime] = None

    class Config:
        from_attributes = True

class AlertOut(BaseModel):
    alert_id: UUID = Field(validation_alias="id")
    ts_opened: datetime
    ts_updated: datetime
    src_ip: str
    severity: str
    status: str
    risk_score: float
    count: int

    class Config:
        from_attributes = True

class AlertDetail(AlertOut):
    details: dict