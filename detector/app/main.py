# detector/app/main.py
from __future__ import annotations

import os
import time
import threading
from queue import Queue, Empty

import torch

from .config import load_config
from .logging_setup import setup_logger
from .mongo import get_mongo, ensure_indexes
from .rtsp_worker import RTSPCameraWorker
from .inference import InferenceConfig, ShopliftingInference
from .clip_builder_segments import select_segments, concat_segments_to_mp4
from .storage import make_clip_filename, clip_path
from .debug_stream import start_debug_server


def clip_worker_loop(*, jobs_queue: Queue, db, clips_dir: str, logger):
    """
    Consumes ClipJob from queue and builds an EXACT clip using FFmpeg segments:
      pre_seconds before the event + during_seconds + post_seconds after
    """
    from datetime import timedelta

    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds between retries

    logger.info("[clip-worker] started (segment-based exact clips)")

    while True:
        try:
            job = jobs_queue.get(timeout=1)
        except Empty:
            continue

        try:
            # Wait so that during/post segments exist on disk
            wait_s = int(job.during_seconds + job.post_seconds)
            if wait_s > 0:
                time.sleep(wait_s)

            start_utc = job.created_at - timedelta(seconds=job.pre_seconds)
            end_utc = job.created_at + timedelta(seconds=job.during_seconds + job.post_seconds)

            # Retry loop: segments may not be flushed to disk yet by FFmpeg
            segments = []
            for attempt in range(1, MAX_RETRIES + 1):
                segments = select_segments(job.segments_dir, start_utc, end_utc)
                if segments:
                    break
                logger.warning(
                    f"[clip-worker] attempt {attempt}/{MAX_RETRIES}: "
                    f"no segments yet for camera={job.camera_id}. Retrying in {RETRY_DELAY}s..."
                )
                time.sleep(RETRY_DELAY)

            if not segments:
                raise RuntimeError(
                    f"No segments found after {MAX_RETRIES} retries for "
                    f"camera={job.camera_id} window={start_utc}->{end_utc}"
                )

            filename = make_clip_filename(job.camera_id, job.created_at)
            out_path = clip_path(clips_dir, filename)

            concat_segments_to_mp4(segments, out_path)

            alert_doc = {
                "eventKey": job.event_key,
                "cameraId": job.camera_id,
                "cameraName": job.camera_name,
                "zone": job.zone,
                "eventType": job.event_type,
                "score": float(job.score),
                "pid": job.pid,
                "createdAt": job.created_at,
                "clip": {
                    "filename": filename,
                    "path": out_path,
                    "source": "ffmpeg_segments",
                    "segmentRange": {
                        "startUtc": start_utc,
                        "endUtc": end_utc,
                    },
                },
            }

            db.alerts.insert_one(alert_doc)
            logger.info(f"[clip-worker] alert stored + clip saved: {filename}")

        except Exception as e:
            logger.exception(f"[clip-worker] failed job {job.job_id}: {e}")
        finally:
            jobs_queue.task_done()


def _start_clip_workers(*, count: int, jobs_queue: Queue, db, clips_dir: str, logger):
    """
    Starts N daemon threads to build clips.
    """
    count = max(1, int(count))
    for i in range(count):
        t = threading.Thread(
            target=clip_worker_loop,
            kwargs=dict(jobs_queue=jobs_queue, db=db, clips_dir=clips_dir, logger=logger),
            daemon=True,
            name=f"clip-worker-{i}",
        )
        t.start()
        logger.info(f"[main] started clip worker: {t.name}")


def _start_camera_workers(*, cfg, db, jobs_queue: Queue, logger, segments_root: str):
    """
    Starts 1 daemon thread per camera:
      - OpenCV read (for inference)
      - FFmpeg segmenter per camera (exact clips)
      - Dedupe (Mongo)
      - Enqueue ClipJob on trigger
    """
    global_cfg = cfg.global_

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"[main] inference device: {device}")

    for cam in cfg.cameras:
        # Per-camera threshold override
        threshold = (
            cam.overrides.threshold
            if cam.overrides and cam.overrides.threshold is not None
            else global_cfg.threshold
        )

        inf_cfg = InferenceConfig(
            device=device,
            win=global_cfg.win,
            d=global_cfg.d,
            consec_windows=global_cfg.consec_windows,
            ema_alpha=global_cfg.ema_alpha,
            yolo_conf=global_cfg.yolo_conf,
            yolo_iou=global_cfg.yolo_iou,
            tracker_path=global_cfg.tracker_path,
            threshold=threshold,
            pose_model_path=cfg.models.pose_model_path,
            classifier_model_path=cfg.models.classifier_model_path,
            anomaly_model_path=cfg.models.anomaly_model_path,
            anomaly_weight=global_cfg.anomaly_weight,
        )

        # Important: Create ONE inference instance per camera to avoid shared tracker state.
        inference = ShopliftingInference(inf_cfg)

        worker = RTSPCameraWorker(
            camera_id=cam.id,
            camera_name=cam.name,
            zone=cam.zone,
            event_type=cam.eventType,
            rtsp_uri=cam.rtsp_uri,
            threshold=threshold,
            fps_target=global_cfg.fps_target,
            frame_width=global_cfg.frame_width,
            frame_height=global_cfg.frame_height,
            dedupe_minutes=global_cfg.dedupe_minutes,
            db=db,
            jobs_queue=jobs_queue,
            logger=logger,
            segments_root=segments_root,
            buffer_seconds=global_cfg.buffer_seconds,
            clip_pre=global_cfg.clip.pre_seconds,
            clip_during=global_cfg.clip.during_seconds,
            clip_post=global_cfg.clip.post_seconds,
            inference=inference,
        )

        t = threading.Thread(
            target=worker.run_forever,
            daemon=True,
            name=f"cam-worker-{cam.id}",
        )
        t.start()

        logger.info(f"[main] started camera worker: {cam.id} ({cam.name}) threshold={threshold}")


def main():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db = os.getenv("MONGO_DB", "shoplifting")
    config_path = os.getenv("CONFIG_PATH", "/config/cameras.yaml")

    clips_dir = os.getenv("CLIPS_DIR", "/shared/clips")
    segments_dir = os.getenv("SEGMENTS_DIR", "/shared/segments")
    log_dir = os.getenv("LOG_DIR", "/shared/logs")

    cfg = load_config(config_path)
    logger = setup_logger(log_dir)

    client, db = get_mongo(mongo_uri, mongo_db)
    ensure_indexes(db)

    # Big queue to absorb bursts (many cameras triggering at once)
    jobs_queue: Queue = Queue(maxsize=50_000)

    # Clip workers: tune based on CPU (mp4 encoding is CPU-heavy)
    clip_workers = int(os.getenv("CLIP_WORKERS", "2"))
    _start_clip_workers(count=clip_workers, jobs_queue=jobs_queue, db=db, clips_dir=clips_dir, logger=logger)

    # Debug MJPEG visualization stream
    debug_port = int(os.getenv("DEBUG_PORT", "9090"))
    start_debug_server(port=debug_port, logger=logger)

    # Start all cameras (1 thread each)
    _start_camera_workers(cfg=cfg, db=db, jobs_queue=jobs_queue, logger=logger, segments_root=segments_dir)

    logger.info("[main] detector running")
    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()