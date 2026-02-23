from __future__ import annotations
import os
import subprocess
import time
import signal
from dataclasses import dataclass
from typing import Optional

@dataclass
class SegmenterConfig:
    rtsp_uri: str
    out_dir: str
    segment_time: int = 1
    keep_seconds: int = 15  # keep > buffer_seconds to be safe
    rtsp_transport: str = "tcp"

class FFMpegSegmenter:
    """
    Runs one FFmpeg process per camera.
    Produces 1-second .ts segments named by epoch seconds:
      <out_dir>/1700000000.ts
    Keeps only last `keep_seconds` files to avoid disk growth.
    """
    def __init__(self, cfg: SegmenterConfig, logger):
        self.cfg = cfg
        self.logger = logger
        self.proc: Optional[subprocess.Popen] = None

    def start(self):
        os.makedirs(self.cfg.out_dir, exist_ok=True)

        # Using epoch seconds (%s). On Linux FFmpeg builds usually support it.
        # Output as MPEG-TS segments (best for concat).
        out_pattern = os.path.join(self.cfg.out_dir, "%s.ts")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-rtsp_transport", self.cfg.rtsp_transport,
            "-i", self.cfg.rtsp_uri,
            "-an",
            "-c:v", "copy",
            "-f", "segment",
            "-segment_time", str(self.cfg.segment_time),
            "-reset_timestamps", "1",
            "-strftime", "1",
            out_pattern,
        ]

        self.logger.info(f"[segmenter] starting ffmpeg segments -> {out_pattern}")
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,  # allow killing process group
        )

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if not self.proc:
            return
        try:
            pgid = os.getpgid(self.proc.pid)
            os.killpg(pgid, signal.SIGTERM)
        except Exception:
            pass

    def cleanup_old_segments(self):
        """
        Deletes old segments beyond keep_seconds.
        """
        try:
            files = [f for f in os.listdir(self.cfg.out_dir) if f.endswith(".ts")]
            # filenames are epoch seconds: "1700000000.ts"
            files_sorted = sorted(files, key=lambda x: int(x.replace(".ts", "")))
            if len(files_sorted) <= self.cfg.keep_seconds:
                return

            to_delete = files_sorted[: max(0, len(files_sorted) - self.cfg.keep_seconds)]
            for f in to_delete:
                try:
                    os.remove(os.path.join(self.cfg.out_dir, f))
                except Exception:
                    pass
        except Exception:
            # best-effort
            pass