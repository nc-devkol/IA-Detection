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
    margin_seconds: int = 3,
) -> List[str]:
    """
    Selects segment files within time range.
    Supports both epoch-second filenames (Linux) and timestamp format (Windows).
    Adds margin to cover FFmpeg buffering delays.
    """
    import platform
    
    # Ensure timezone-aware datetimes
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=timezone.utc)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=timezone.utc)
    
    start_s = _epoch_seconds(start_utc) - margin_seconds
    end_s = _epoch_seconds(end_utc) + margin_seconds

    paths = []
    
    # Try to find segments - support both naming conventions
    if platform.system() == "Windows":
        # Windows format: 20260223_143055.ts
        # List all .ts files and filter by modification time
        if not os.path.exists(segments_dir):
            return paths
        
        all_files = [f for f in os.listdir(segments_dir) if f.endswith('.ts')]
        for fname in sorted(all_files):
            fpath = os.path.join(segments_dir, fname)
            try:
                # Use file modification time as proxy for segment time
                mtime = os.path.getmtime(fpath)
                if start_s <= mtime <= end_s:
                    paths.append(fpath)
            except Exception:
                continue
    else:
        # Linux format: epoch.ts
        for sec in range(start_s, end_s + 1):
            p = os.path.join(segments_dir, f"{sec}.ts")
            if os.path.exists(p):
                paths.append(p)
    
    return sorted(paths)

def concat_segments_to_mp4(segment_paths: List[str], out_mp4: str) -> None:
    """
    Safe MVP approach: re-encode to mp4 to avoid timestamp/codec edge cases.
    """
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    if not segment_paths:
        raise RuntimeError("No segments found to build clip")

    print(f"[concat_segments_to_mp4] Concatenating {len(segment_paths)} segments:")
    for i, seg in enumerate(segment_paths[:5]):  # Show first 5
        print(f"  [{i}] {seg}")
    if len(segment_paths) > 5:
        print(f"  ... and {len(segment_paths) - 5} more")

    with tempfile.TemporaryDirectory() as tmp:
        list_file = os.path.join(tmp, "list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for p in segment_paths:
                # Escape path for FFmpeg concat
                escaped = p.replace("\\", "/")
                f.write(f"file '{escaped}'\n")

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
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[concat_segments_to_mp4] FFmpeg error: {result.stderr}")
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")