from __future__ import annotations
import calendar
import os
import math
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from typing import List, Tuple


def _epoch_seconds(dt: datetime) -> int:
    """
    Convert a datetime to epoch seconds.
    Handles naive datetimes (assumed UTC) and aware datetimes correctly.
    """
    if dt.tzinfo is None:
        # Naive datetime — treat as UTC explicitly via calendar.timegm
        return int(calendar.timegm(dt.timetuple()))
    return int(dt.timestamp())


def select_segments(
    segments_dir: str,
    start_utc: datetime,
    end_utc: datetime,
    margin_seconds: int = 2,
) -> List[str]:
    """
    Selects segment files by epoch-second filenames: <epoch>.ts
    Adds a small margin on each side to cover FFmpeg buffering delays.
    """
    start_s = _epoch_seconds(start_utc) - margin_seconds
    end_s = _epoch_seconds(end_utc) + margin_seconds

    paths = []
    for sec in range(start_s, end_s + 1):
        p = os.path.join(segments_dir, f"{sec}.ts")
        if os.path.exists(p):
            paths.append(p)
    return paths

def concat_segments_to_mp4(segment_paths: List[str], out_mp4: str) -> None:
    """
    Safe MVP approach: re-encode to mp4 to avoid timestamp/codec edge cases.
    """
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    if not segment_paths:
        raise RuntimeError("No segments found to build clip")

    with tempfile.TemporaryDirectory() as tmp:
        list_file = os.path.join(tmp, "list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for p in segment_paths:
                f.write(f"file '{p}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            out_mp4,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)