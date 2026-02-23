from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ClipJob:
    job_id: str
    camera_id: str
    camera_name: str
    zone: str
    event_type: str
    event_key: str
    score: float
    pid: int | None
    created_at: datetime  # UTC
    segments_dir: str
    pre_seconds: int
    during_seconds: int
    post_seconds: int