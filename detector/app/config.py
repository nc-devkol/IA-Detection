from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import yaml
import os

class ClipConfig(BaseModel):
    pre_seconds: int = 2
    during_seconds: int = 2
    post_seconds: int = 2

class GlobalConfig(BaseModel):
    threshold: float = 0.65
    buffer_seconds: int = 10
    dedupe_minutes: int = 5
    fps_target: int = 30  # Aumentado de 15 a 30 para procesar más frames
    frame_width: int = 1280  # Aumentado de 640 a 1280 para mejor detección
    frame_height: int = 720  # Aumentado de 360 a 720 para mejor detección
    jpeg_quality: int = 75
    clip: ClipConfig = Field(default_factory=ClipConfig)
    win: int = 24
    d: int = 34
    consec_windows: int = 5
    ema_alpha: float = 0.6
    yolo_conf: float = 0.15
    yolo_iou: float = 0.5
    tracker_path: str = "/models/bytetrack.yaml"
    anomaly_weight: float = 0.3  # weight for anomaly AE in combined score

class ModelsConfig(BaseModel):
    pose_model_path: str
    anomaly_model_path: Optional[str] = None
    classifier_model_path: str

class CameraOverrides(BaseModel):
    threshold: Optional[float] = None

class CameraConfig(BaseModel):
    id: str
    name: str
    zone: str
    eventType: str
    rtsp_uri: str
    overrides: Optional[CameraOverrides] = None

class AppConfig(BaseModel):
    global_: GlobalConfig = Field(alias="global")
    models: ModelsConfig
    cameras: List[CameraConfig]

def load_config(path: str) -> AppConfig:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return AppConfig.model_validate(raw)