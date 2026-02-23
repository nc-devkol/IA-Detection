# detector/app/dedupe.py
from __future__ import annotations

from datetime import datetime, timedelta
from pymongo.database import Database


def build_event_key(camera_id: str, zone: str, event_type: str) -> str:
    """
    Stable dedupe key for CCTV environments.
    We avoid using person IDs because trackers can switch IDs.
    """
    return f"{camera_id}|{zone}|{event_type}"


def is_duplicate(db: Database, event_key: str, window_minutes: int) -> bool:
    """
    Returns True if an alert with the same event_key exists within the last `window_minutes`.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)

    doc = db.alerts.find_one(
        {"eventKey": event_key, "createdAt": {"$gte": cutoff}},
        projection={"_id": 1},
    )
    return doc is not None