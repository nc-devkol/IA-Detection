from __future__ import annotations
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from bson import ObjectId
from typing import List

from .mongo import get_db
from .schemas import AlertOut

app = FastAPI(title="Shoplifting MVP API")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "shoplifting")
CLIPS_DIR = os.getenv("CLIPS_DIR", "/shared/clips")

db = get_db(MONGO_URI, MONGO_DB)

def _oid(x: str) -> ObjectId:
    try:
        return ObjectId(x)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")

def _doc_to_alert(d: dict) -> dict:
    """Convert Mongo doc to a dict compatible with AlertOut."""
    d["id"] = str(d.pop("_id"))
    return d

@app.get("/alerts", response_model=List[AlertOut])
def list_alerts(limit: int = 50):
    docs = list(db.alerts.find({}, sort=[("createdAt", -1)], limit=min(limit, 200)))
    return [_doc_to_alert(d) for d in docs]

@app.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: str):
    d = db.alerts.find_one({"_id": _oid(alert_id)})
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    return _doc_to_alert(d)

@app.get("/alerts/{alert_id}/clip")
def download_clip(alert_id: str):
    d = db.alerts.find_one({"_id": _oid(alert_id)}, projection={"clip": 1})
    if not d or "clip" not in d:
        raise HTTPException(status_code=404, detail="Clip not found")
    filename = d["clip"]["filename"]
    path = os.path.join(CLIPS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Clip file missing on disk")
    return FileResponse(path, media_type="video/mp4", filename=filename)