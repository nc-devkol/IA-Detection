from __future__ import annotations
import os
from datetime import datetime
import uuid

def make_clip_filename(camera_id: str, created_at: datetime) -> str:
    ts = created_at.strftime("%Y%m%d_%H%M%S")
    return f"{camera_id}_{ts}_{uuid.uuid4().hex[:8]}.mp4"

def clip_path(clips_dir: str, filename: str) -> str:
    os.makedirs(clips_dir, exist_ok=True)
    return os.path.join(clips_dir, filename)