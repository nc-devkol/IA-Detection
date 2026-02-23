"""
MJPEG debug stream server.
Serves annotated frames (bboxes, keypoints, scores) over HTTP.
Open http://localhost:9090 in a browser to see live detections.
"""
from __future__ import annotations

import threading
import time
import cv2
import numpy as np
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Dict, Optional

# ---- Skeleton connections (COCO 17-keypoint) ----
SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),        # head
    (5, 6),                                   # shoulders
    (5, 7), (7, 9),                           # left arm
    (6, 8), (8, 10),                          # right arm
    (5, 11), (6, 12),                         # torso
    (11, 12),                                 # hips
    (11, 13), (13, 15),                       # left leg
    (12, 14), (14, 16),                       # right leg
]

# Colors
GREEN  = (0, 255, 0)
YELLOW = (0, 255, 255)
RED    = (0, 0, 255)
WHITE  = (255, 255, 255)
CYAN   = (255, 255, 0)


class FrameStore:
    """Thread-safe store for the latest annotated frame per camera, with change notification."""

    def __init__(self):
        self._frames: Dict[str, bytes] = {}   # camera_id -> JPEG bytes
        self._versions: Dict[str, int] = {}   # camera_id -> frame version counter
        self._lock = threading.Lock()
        self._event = threading.Event()        # signaled on every new frame

    def update(self, camera_id: str, jpeg_bytes: bytes):
        with self._lock:
            self._frames[camera_id] = jpeg_bytes
            self._versions[camera_id] = self._versions.get(camera_id, 0) + 1
        self._event.set()    # wake up any waiting stream handlers

    def get(self, camera_id: str) -> Optional[bytes]:
        with self._lock:
            return self._frames.get(camera_id)

    def get_version(self, camera_id: str) -> int:
        with self._lock:
            return self._versions.get(camera_id, 0)

    def wait_for_new_frame(self, timeout: float = 0.2):
        """Block until a new frame arrives (any camera) or timeout."""
        self._event.wait(timeout=timeout)
        self._event.clear()

    def get_all_ids(self):
        with self._lock:
            return list(self._frames.keys())


# Global singleton
_frame_store = FrameStore()


def get_frame_store() -> FrameStore:
    return _frame_store


def annotate_frame(
    frame: np.ndarray,
    results,
    ema_scores: Dict[int, float],
    consec_hits: Dict[int, int],
    consec_windows: int,
    threshold: float,
    camera_id: str,
) -> np.ndarray:
    """
    Draw bounding boxes, keypoints, skeleton, PID/score on the frame.
    """
    annotated = frame.copy()
    h, w = annotated.shape[:2]

    r = results[0]
    if r.boxes is None or r.keypoints is None:
        # No detections — just draw header
        _draw_header(annotated, camera_id, threshold, 0)
        return annotated

    ids = r.boxes.id
    if ids is None:
        _draw_header(annotated, camera_id, threshold, 0)
        return annotated

    ids_np = ids.cpu().numpy().astype(int)
    boxes = r.boxes.xyxy.cpu().numpy()
    kps_xy = r.keypoints.xy.cpu().numpy()
    kps_conf = r.keypoints.conf.cpu().numpy()

    for pid, box, xy, conf in zip(ids_np, boxes, kps_xy, kps_conf):
        score = ema_scores.get(pid, 0.0)
        consec = consec_hits.get(pid, 0)

        # Color based on score
        if score >= threshold:
            color = RED
        elif score >= threshold * 0.5:
            color = YELLOW
        else:
            color = GREEN

        # Bounding box
        x1, y1, x2, y2 = box.astype(int)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        # Label: PID + score + consec
        label = f"#{pid} {score:.2f} [{consec}/{consec_windows}]"
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, y1 - label_size[1] - 8), (x1 + label_size[0] + 4, y1), color, -1)
        cv2.putText(annotated, label, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)

        # Keypoints + skeleton
        _draw_skeleton(annotated, xy, conf, color)

    _draw_header(annotated, camera_id, threshold, len(ids_np))
    return annotated


def _draw_skeleton(frame, xy, conf, color, min_conf=0.25):
    """Draw keypoints and skeleton lines."""
    pts = []
    for i, (x, y) in enumerate(xy):
        c = conf[i] if i < len(conf) else 0
        if c >= min_conf:
            cv2.circle(frame, (int(x), int(y)), 3, CYAN, -1)
            pts.append((int(x), int(y), True))
        else:
            pts.append((0, 0, False))

    for i, j in SKELETON:
        if i < len(pts) and j < len(pts) and pts[i][2] and pts[j][2]:
            cv2.line(frame, (pts[i][0], pts[i][1]), (pts[j][0], pts[j][1]), color, 1)


def _draw_header(frame, camera_id, threshold, num_tracked):
    """Draw top-left info bar."""
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 28), (0, 0, 0), -1)
    ts = time.strftime("%H:%M:%S")
    text = f"{camera_id} | thr={threshold:.2f} | tracked={num_tracked} | {ts}"
    cv2.putText(frame, text, (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)


# ---- MJPEG HTTP Server ----

class MJPEGHandler(BaseHTTPRequestHandler):
    """Serves MJPEG stream and a simple index page."""

    def log_message(self, format, *args):
        pass  # suppress request logs

    def do_GET(self):
        store = get_frame_store()

        if self.path == "/" or self.path == "/index.html":
            self._serve_index(store)
        elif self.path.startswith("/stream/"):
            cam_id = self.path.split("/stream/", 1)[1].rstrip("/")
            self._serve_stream(store, cam_id)
        elif self.path == "/stream" or self.path == "/stream/":
            # Default: first camera
            ids = store.get_all_ids()
            if ids:
                self._serve_stream(store, ids[0])
            else:
                self.send_error(404, "No cameras available yet")
        else:
            self.send_error(404)

    def _serve_index(self, store: FrameStore):
        ids = store.get_all_ids()
        html = "<html><head><title>Shoplifting Detector - Debug</title>"
        html += "<style>body{background:#111;color:#eee;font-family:monospace;margin:20px}"
        html += "h1{color:#0f0} img{border:2px solid #333;margin:10px}</style></head><body>"
        html += "<h1>Shoplifting Detector - Live Debug</h1>"
        if not ids:
            html += "<p>Waiting for cameras to connect...</p>"
            html += '<script>setTimeout(()=>location.reload(),3000)</script>'
        else:
            for cam_id in sorted(ids):
                html += f'<h2>{cam_id}</h2>'
                html += f'<img src="/stream/{cam_id}" width="640" height="360" />'
        html += "</body></html>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_stream(self, store: FrameStore, cam_id: str):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        last_version = 0
        try:
            while True:
                cur_version = store.get_version(cam_id)
                if cur_version == last_version:
                    # Wait for a new frame instead of busy-polling
                    store.wait_for_new_frame(timeout=0.15)
                    continue

                jpeg = store.get(cam_id)
                if jpeg is None:
                    store.wait_for_new_frame(timeout=0.15)
                    continue

                last_version = cur_version
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


def start_debug_server(port: int = 9090, logger=None):
    """Start the MJPEG debug server in a daemon thread."""

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True   # all handler threads are daemons

    def _run():
        server = ThreadedHTTPServer(("0.0.0.0", port), MJPEGHandler)
        if logger:
            logger.info(f"[debug-stream] MJPEG server started on http://0.0.0.0:{port}")
        server.serve_forever()

    t = threading.Thread(target=_run, daemon=True, name="debug-stream")
    t.start()
    return t
