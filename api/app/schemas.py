from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any

class SegmentRange(BaseModel):
    startUtc: Optional[datetime] = None
    endUtc: Optional[datetime] = None

class ClipInfo(BaseModel):
    filename: str
    path: str
    source: Optional[str] = None
    segmentRange: Optional[SegmentRange] = None

class AlertOut(BaseModel):
    id: str
    eventKey: str
    cameraId: str
    cameraName: str
    zone: str
    eventType: str
    score: float
    pid: Optional[int] = None
    createdAt: datetime
    clip: Optional[ClipInfo] = None