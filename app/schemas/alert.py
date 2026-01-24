from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

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