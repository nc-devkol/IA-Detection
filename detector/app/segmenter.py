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

        # Windows-compatible: use %Y%m%d%H%M%S format then convert via strftime_mkdir_p
        # Actually, better: use segment_format_options with epoch time
        # Most reliable: use %s but ensure FFmpeg build supports it, fallback to manual naming
        import platform
        if platform.system() == "Windows":
            # Windows: use timestamp format that works
            out_pattern = os.path.join(self.cfg.out_dir, "%Y%m%d_%H%M%S.ts")
        else:
            # Linux: use epoch seconds
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
        
        # Platform-specific process creation
        import platform
        if platform.system() == "Windows":
            # Windows: no preexec_fn
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,  # Capture stderr for debugging
            )
        else:
            # Unix: use setsid for process group management
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
            )

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if not self.proc:
            return
        try:
            import platform
            if platform.system() == "Windows":
                # Windows: terminate directly
                self.proc.terminate()
                self.proc.wait(timeout=5)
            else:
                # Unix: kill process group
                pgid = os.getpgid(self.proc.pid)
                os.killpg(pgid, signal.SIGTERM)
        except Exception as e:
            self.logger.warning(f"[segmenter] error stopping: {e}")
            try:
                self.proc.kill()
            except Exception:
                pass

    def cleanup_old_segments(self):
        """
        Deletes old segments beyond keep_seconds.
        """
        try:
            if not os.path.exists(self.cfg.out_dir):
                return
                
            files = [f for f in os.listdir(self.cfg.out_dir) if f.endswith(".ts")]
            if len(files) <= self.cfg.keep_seconds:
                return

            # Sort by modification time (works for both naming schemes)
            files_with_mtime = []
            for f in files:
                fpath = os.path.join(self.cfg.out_dir, f)
                try:
                    mtime = os.path.getmtime(fpath)
                    files_with_mtime.append((f, mtime))
                except Exception:
                    continue
            
            # Keep newest N files
            files_with_mtime.sort(key=lambda x: x[1])
            to_delete = files_with_mtime[: max(0, len(files_with_mtime) - self.cfg.keep_seconds)]
            
            for fname, _ in to_delete:
                try:
                    os.remove(os.path.join(self.cfg.out_dir, fname))
                except Exception:
                    pass
        except Exception:
            # best-effort
            pass