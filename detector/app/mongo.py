from __future__ import annotations
from pymongo import MongoClient, ASCENDING
from datetime import datetime

def get_mongo(mongo_uri: str, db_name: str):
    client = MongoClient(mongo_uri)
    db = client[db_name]
    return client, db

def ensure_indexes(db):
    alerts = db.alerts
    # For querying recent events by key + createdAt
    alerts.create_index([("eventKey", ASCENDING), ("createdAt", ASCENDING)])
    alerts.create_index([("createdAt", ASCENDING)])