from __future__ import annotations
import time
import numpy as np
import torch
import torch.nn as nn
from dataclasses import dataclass
from collections import defaultdict, deque
from typing import Any, Dict, Optional, Set

from ultralytics import YOLO

# ===== Pose normalization indices (your lab) =====
L_SH, R_SH, L_HIP, R_HIP = 5, 6, 11, 12

def normalize_kps(kps_17x3: np.ndarray, min_conf: float = 0.25) -> Optional[np.ndarray]:
    xy = kps_17x3[:, :2].astype(np.float32)
    cf = kps_17x3[:, 2].astype(np.float32)

    if (cf[[L_SH, R_SH, L_HIP, R_HIP]].mean()) < min_conf:
        return None

    hip = (xy[L_HIP] + xy[R_HIP]) / 2.0
    shoulder = (xy[L_SH] + xy[R_SH]) / 2.0

    scale = np.linalg.norm(shoulder - hip)
    if scale < 1e-3:
        return None

    xy = (xy - hip) / (scale + 1e-6)
    return xy.reshape(-1).astype(np.float32)  # D = 34


class PoseAutoEncoder(nn.Module):
    """
    LSTM-based sequence autoencoder for pose anomaly detection.
    High reconstruction error = anomalous (suspicious) pose sequence.
    Architecture from pose_ae.pt: Encoder LSTM(34,128) -> Decoder LSTM(128,128) -> Linear(128,34)
    """
    def __init__(self, d: int = 34, hidden: int = 128):
        super().__init__()
        self.hidden = hidden
        self.encoder = nn.LSTM(d, hidden, batch_first=True)
        self.decoder = nn.LSTM(hidden, hidden, batch_first=True)
        self.out = nn.Linear(hidden, d)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, WIN, D)
        _, (h, c) = self.encoder(x)                       # encode full sequence
        # Repeat last hidden state across all time steps for decoder input
        dec_in = h.permute(1, 0, 2).repeat(1, x.size(1), 1)  # (B, WIN, hidden)
        dec_out, _ = self.decoder(dec_in, (h, c))
        return self.out(dec_out)                           # (B, WIN, D) reconstructed

    def reconstruction_error(self, x: torch.Tensor) -> torch.Tensor:
        """Returns per-sample mean squared reconstruction error. Shape: (B,)"""
        x_hat = self.forward(x)
        return ((x - x_hat) ** 2).mean(dim=(1, 2))        # MSE per sample


class TCNClassifier(nn.Module):
    def __init__(self, d: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(d, 64, 3, padding=1),
            nn.ReLU(),
            nn.Conv1d(64, 128, 3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1)
        )
        self.fc = nn.Linear(128, 2)

    def forward(self, x):
        # x: (B, WIN, D) -> Conv1d expects (B, D, WIN)
        x = x.permute(0, 2, 1)
        x = self.net(x).squeeze(-1)
        return self.fc(x)


@dataclass
class InferenceConfig:
    device: str
    win: int
    d: int
    consec_windows: int
    ema_alpha: float
    yolo_conf: float
    yolo_iou: float
    tracker_path: str
    threshold: float
    pose_model_path: str
    classifier_model_path: str
    anomaly_model_path: Optional[str] = None   # path to pose_ae.pt
    anomaly_weight: float = 0.3                # weight for anomaly score in combo


@dataclass
class InferenceOutput:
    triggered: bool
    score: float
    pid: Optional[int]
    debug: Dict[str, Any]


class ShopliftingInference:
    """
    Implements your lab logic:
      YOLO pose track -> normalize_kps -> buffer WIN -> TCN -> softmax prob[1]
      EMA smoothing + consecutive windows gate
    """
    def __init__(self, cfg: InferenceConfig):
        self.cfg = cfg
        self.device = cfg.device

        self.pose_model = YOLO(cfg.pose_model_path)

        self.clf = TCNClassifier(cfg.d).to(cfg.device)
        state = torch.load(cfg.classifier_model_path, map_location=cfg.device)
        self.clf.load_state_dict(state)
        self.clf.eval()

        # Anomaly autoencoder (optional — combined with TCN when available)
        self.anomaly_model: Optional[PoseAutoEncoder] = None
        if cfg.anomaly_model_path:
            self.anomaly_model = PoseAutoEncoder(d=cfg.d).to(cfg.device)
            ae_state = torch.load(cfg.anomaly_model_path, map_location=cfg.device)
            self.anomaly_model.load_state_dict(ae_state)
            self.anomaly_model.eval()
            # Calibration: running stats for normalizing reconstruction error to [0,1]
            self._ae_ema_mean: float = 0.0
            self._ae_ema_var: float = 1.0
            self._ae_calibrated: bool = False
            self._ae_warmup_errors: list = []  # collect first N errors for init
            self._ae_warmup_n: int = 50

        self.pose_buffers: Dict[int, deque] = defaultdict(lambda: deque(maxlen=cfg.win))
        self.consec_hits: Dict[int, int] = defaultdict(int)
        self.ema_score: Dict[int, float] = defaultdict(float)

        # Stale ID cleanup
        self._last_seen: Dict[int, float] = {}          # pid -> last time.time()
        self._stale_timeout: float = 30.0                # seconds without seeing a pid
        self._last_cleanup: float = time.time()
        self._cleanup_interval: float = 10.0             # run cleanup every N seconds

        # Periodic YOLO tracker reset to avoid unbounded internal state
        self._frame_count: int = 0
        self._tracker_reset_interval: int = 15 * 60 * cfg.win  # ~every 15 min worth of windows

    def _cleanup_stale_ids(self, active_ids: Set[int]) -> int:
        """Remove tracking data for person IDs not seen recently. Returns count removed."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return 0

        self._last_cleanup = now
        stale = [
            pid for pid, last_t in self._last_seen.items()
            if pid not in active_ids and (now - last_t) > self._stale_timeout
        ]
        for pid in stale:
            self.pose_buffers.pop(pid, None)
            self.consec_hits.pop(pid, None)
            self.ema_score.pop(pid, None)
            self._last_seen.pop(pid, None)
        return len(stale)

    @torch.no_grad()
    def step(self, frame_bgr: np.ndarray) -> InferenceOutput:
        self._frame_count += 1

        # Periodic tracker reset to prevent unbounded YOLO internal state
        persist = True
        if self._frame_count % self._tracker_reset_interval == 0:
            persist = False  # resets YOLO internal tracker state
            self.pose_buffers.clear()
            self.consec_hits.clear()
            self.ema_score.clear()
            self._last_seen.clear()

        results = self.pose_model.track(
            frame_bgr,
            persist=persist,
            tracker=self.cfg.tracker_path,
            conf=self.cfg.yolo_conf,
            iou=self.cfg.yolo_iou,
            verbose=False,
        )

        r = results[0]
        triggered = False
        best_score = 0.0
        best_pid = None
        seen = 0
        active_ids: Set[int] = set()

        if r.boxes is not None and r.keypoints is not None:
            ids = r.boxes.id
            if ids is not None:
                ids = ids.cpu().numpy().astype(int)
                xy = r.keypoints.xy.cpu().numpy()
                cf = r.keypoints.conf.cpu().numpy()
                seen = len(ids)
                active_ids = set(ids)

                now = time.time()
                for pid, xy_i, cf_i in zip(ids, xy, cf):
                    self._last_seen[pid] = now

                    kps = np.concatenate([xy_i, cf_i[:, None]], axis=1)
                    vec = normalize_kps(kps)
                    if vec is None:
                        continue

                    self.pose_buffers[pid].append(vec)

                    if len(self.pose_buffers[pid]) == self.cfg.win:
                        x = np.stack(self.pose_buffers[pid], axis=0)  # (WIN, D)
                        xt = torch.tensor(x, dtype=torch.float32, device=self.cfg.device).unsqueeze(0)

                        # ----- TCN classifier score -----
                        logits = self.clf(xt)
                        tcn_prob = torch.softmax(logits, dim=1)[0, 1].item()

                        # ----- Anomaly autoencoder score -----
                        anomaly_prob = 0.0
                        if self.anomaly_model is not None:
                            anomaly_prob = self._anomaly_score(xt)

                        # ----- Combined score -----
                        if self.anomaly_model is not None:
                            w = self.cfg.anomaly_weight
                            prob = (1 - w) * tcn_prob + w * anomaly_prob
                        else:
                            prob = tcn_prob

                        self.ema_score[pid] = self.cfg.ema_alpha * prob + (1 - self.cfg.ema_alpha) * self.ema_score[pid]

                        if self.ema_score[pid] >= self.cfg.threshold:
                            self.consec_hits[pid] += 1
                        else:
                            self.consec_hits[pid] = 0

                        # Gate with consecutive windows
                        if self.consec_hits[pid] >= self.cfg.consec_windows:
                            triggered = True
                            if self.ema_score[pid] > best_score:
                                best_score = self.ema_score[pid]
                                best_pid = pid

        # --- Passive decay: for PIDs NOT seen this frame, decay EMA toward 0 ---
        decay_rate = 0.85  # each frame without detection, EMA *= 0.85
        for pid in list(self.ema_score.keys()):
            if pid not in active_ids:
                self.ema_score[pid] *= decay_rate
                self.consec_hits[pid] = 0
                # If decayed below a negligible value, clear the pose buffer too
                if self.ema_score[pid] < 0.01:
                    self.ema_score[pid] = 0.0
                    self.pose_buffers.pop(pid, None)

        # Periodically purge stale IDs to prevent memory leak
        cleaned = self._cleanup_stale_ids(active_ids)

        return InferenceOutput(
            triggered=triggered,
            score=float(best_score),
            pid=best_pid,
            debug={"tracked_ids": seen, "cleaned_ids": cleaned, "_raw_results": results},
        )

    def _anomaly_score(self, xt: torch.Tensor) -> float:
        """
        Compute normalized anomaly score from autoencoder reconstruction error.
        Uses online z-score normalization and sigmoid to map to [0, 1].
        """
        raw_err = self.anomaly_model.reconstruction_error(xt).item()

        # Warmup phase: collect errors to initialize running stats
        if not self._ae_calibrated:
            self._ae_warmup_errors.append(raw_err)
            if len(self._ae_warmup_errors) >= self._ae_warmup_n:
                self._ae_ema_mean = float(np.mean(self._ae_warmup_errors))
                self._ae_ema_var = max(float(np.var(self._ae_warmup_errors)), 1e-6)
                self._ae_calibrated = True
            # During warmup return 0 (no anomaly contribution)
            return 0.0

        # Online update of running mean/variance (EMA)
        alpha = 0.01
        self._ae_ema_mean = (1 - alpha) * self._ae_ema_mean + alpha * raw_err
        self._ae_ema_var = (1 - alpha) * self._ae_ema_var + alpha * (raw_err - self._ae_ema_mean) ** 2

        # Z-score -> sigmoid to get probability in [0, 1]
        std = max(self._ae_ema_var ** 0.5, 1e-6)
        z = (raw_err - self._ae_ema_mean) / std
        score = 1.0 / (1.0 + np.exp(-z))  # sigmoid
        return float(np.clip(score, 0.0, 1.0))