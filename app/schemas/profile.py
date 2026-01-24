from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class ProfileOut(BaseModel):
    trap_id: str
    src_ip: str
    risk_score: float
    last_seen: Optional[datetime] = None

    class Config:
        from_attributes = True