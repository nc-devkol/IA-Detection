from __future__ import annotations
import time
import uuid
import cv2
from datetime import datetime, timedelta
from queue import Queue
from typing import Optional

from .dedupe import build_event_key, is_duplicate
from .jobs import ClipJob
from .segmenter import FFMpegSegmenter, SegmenterConfig
from .inference import ShopliftingInference
from .debug_stream import annotate_frame, get_frame_store

class RTSPCameraWorker:
    def __init__(
        self,
        *,
        camera_id: str,
        camera_name: str,
        zone: str,
        event_type: str,
        rtsp_uri: str,
        threshold: float,
        fps_target: int,
        frame_width: int,
        frame_height: int,
        dedupe_minutes: int,
        db,
        jobs_queue: Queue,
        logger,
        segments_root: str,
        buffer_seconds: int,
        clip_pre: int,
        clip_during: int,
        clip_post: int,
        inference: ShopliftingInference,
        reconnect_sleep: float = 2.0,
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.zone = zone
        self.event_type = event_type
        self.rtsp_uri = rtsp_uri
        self.threshold = threshold
        self.fps_target = fps_target
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.dedupe_minutes = dedupe_minutes
        self.db = db
        self.jobs_queue = jobs_queue
        self.logger = logger
        self.reconnect_sleep = reconnect_sleep

        self.clip_pre = clip_pre
        self.clip_during = clip_during
        self.clip_post = clip_post

        self.segments_dir = f"{segments_root}/{camera_id}"
        keep = max(buffer_seconds + clip_pre + clip_during + clip_post + 5, 15)
        self.segmenter = FFMpegSegmenter(
            SegmenterConfig(
                rtsp_uri=rtsp_uri,
                out_dir=self.segments_dir,
                segment_time=1,
                keep_seconds=keep,
            ),
            logger=logger,
        )

        self.inference = inference

    def _open_cv(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(self.rtsp_uri, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)       # minimize internal buffer
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"H264"))
        return cap

    def _drain_buffer(self, cap: cv2.VideoCapture, max_grabs: int = 5):
        """Drain stale frames from OpenCV's internal buffer without decoding."""
        for _ in range(max_grabs):
            if not cap.grab():
                break

    def run_forever(self):
        # Ensure segmenter is running
        if not self.segmenter.is_running():
            self.segmenter.start()

        frame_interval = 1.0 / max(1, self.fps_target)
        last_frame_ts = 0.0
        last_score_log_ts = 0.0
        SCORE_LOG_INTERVAL = 3.0  # seconds between score dumps

        while True:
            cap = self._open_cv()
            if not cap.isOpened():
                self.logger.warning(f"[{self.camera_id}] OpenCV RTSP open failed. Retrying...")
                time.sleep(self.reconnect_sleep)
                continue

            self.logger.info(f"[{self.camera_id}] OpenCV RTSP connected.")
            try:
                while True:
                    now = time.time()
                    elapsed = now - last_frame_ts

                    # If not time to process yet, grab (don't decode) to flush buffer
                    if elapsed < frame_interval:
                        cap.grab()   # discard frame without decoding — keeps buffer fresh
                        continue

                    # Drain any remaining stale frames, then decode the freshest one
                    self._drain_buffer(cap)
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        self.logger.warning(f"[{self.camera_id}] OpenCV RTSP read failed. Reconnecting...")
                        break

                    last_frame_ts = time.time()  # use actual time after read

                    # Keep segmenter alive + cleanup
                    if not self.segmenter.is_running():
                        self.logger.warning(f"[{self.camera_id}] Segmenter stopped. Restarting...")
                        self.segmenter.start()
                    self.segmenter.cleanup_old_segments()

                    # Resize for inference
                    frame = cv2.resize(frame, (self.frame_width, self.frame_height))

                    out = self.inference.step(frame)

                    # --- Push annotated frame to debug MJPEG stream ---
                    try:
                        annotated = annotate_frame(
                            frame,
                            out.debug.get("_raw_results"),
                            self.inference.ema_score,
                            self.inference.consec_hits,
                            self.inference.cfg.consec_windows,
                            self.threshold,
                            self.camera_id,
                        )
                        _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        get_frame_store().update(self.camera_id, jpeg.tobytes())
                    except Exception:
                        pass  # never crash the worker for debug viz

                    # --- Periodic score dump (every 3s) ---
                    if now - last_score_log_ts >= SCORE_LOG_INTERVAL:
                        last_score_log_ts = now
                        ema = self.inference.ema_score
                        consec = self.inference.consec_hits
                        if ema:
                            lines = " | ".join(
                                f"pid={pid} score={ema[pid]:.3f} consec={consec.get(pid,0)}/{self.inference.cfg.consec_windows}"
                                for pid in sorted(ema.keys())
                            )
                            self.logger.info(
                                f"[{self.camera_id}] threshold={self.threshold:.2f} | {lines}"
                            )

                    if not out.triggered:
                        continue

                    event_time = datetime.utcnow()
                    event_key = build_event_key(self.camera_id, self.zone, self.event_type)

                    # Dedupe (MVP)
                    self.logger.debug(f"Checking duplicate for event_key={event_key} at {event_time.isoformat()}")
                    if is_duplicate(self.db, event_key, self.dedupe_minutes):
                        self.logger.info(f"[{self.camera_id}] Duplicate event ignored ({event_key}).")
                        continue

                    job = ClipJob(
                        job_id=uuid.uuid4().hex,
                        camera_id=self.camera_id,
                        camera_name=self.camera_name,
                        zone=self.zone,
                        event_type=self.event_type,
                        event_key=event_key,
                        score=out.score if out.score > 0 else self.threshold,
                        pid=out.pid,
                        created_at=event_time,
                        segments_dir=self.segments_dir,
                        pre_seconds=self.clip_pre,
                        during_seconds=self.clip_during,
                        post_seconds=self.clip_post,
                    )

                    self.jobs_queue.put(job)
                    self.logger.info(
                        f"[{self.camera_id}] Clip job enqueued. pid={out.pid} score={job.score:.3f}"
                    )

            except Exception as e:
                self.logger.exception(f"[{self.camera_id}] Worker exception: {e}")
            finally:
                cap.release()
                time.sleep(self.reconnect_sleep)