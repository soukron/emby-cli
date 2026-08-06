"""Path, size, skip, and ffmpeg helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

from emby_cli.constants import TICKS_PER_SECOND

def build_dest_path(item: dict, output_dir: Path) -> Path:
    """Build a destination path that mirrors the Emby library structure."""
    server_path = item.get("Path", "")
    if server_path:
        # Use the last 2-3 path components (e.g. Movies/Title/file.mkv)
        parts = Path(server_path).parts
        # Take from the library-level folder onward (heuristic: skip leading /downloads, /mnt, etc.)
        relevant = parts[-3:] if len(parts) >= 3 else parts[-2:] if len(parts) >= 2 else parts
        return output_dir / Path(*relevant)

    name = item.get("Name", item["Id"])
    ext = ".mkv"
    sources = item.get("MediaSources", [])
    if sources and sources[0].get("Container"):
        ext = "." + sources[0]["Container"]
    return output_dir / f"{name}{ext}"


def item_duration_seconds(item: dict) -> float | None:
    ticks = item.get("RunTimeTicks")
    if ticks:
        return ticks / TICKS_PER_SECOND
    return None


def item_playback_rate(item: dict) -> float | None:
    """Bytes per second that matches real-time playback speed."""
    size = item_remote_size(item)
    duration = item_duration_seconds(item)
    if size and duration and duration > 0:
        return size / duration
    return None


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s"


def item_remote_size(item: dict) -> int | None:
    sources = item.get("MediaSources", [])
    if sources:
        return sources[0].get("Size")
    return None


def format_size(n: int | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} PiB"


def should_skip(item: dict, dest: Path) -> bool:
    """Return True when the local file already matches the remote size."""
    if not dest.exists():
        return False
    remote_size = item_remote_size(item)
    if remote_size is None:
        return False
    return dest.stat().st_size == remote_size


def should_skip_hls(dest: Path) -> bool:
    """Skip only if the .mkv AND its .done marker both exist."""
    mkv = dest.with_suffix(".mkv")
    done = Path(str(mkv) + ".done")
    return mkv.exists() and done.exists()


def ffmpeg_exe() -> str:
    """Return the bundled static-ffmpeg binary (never the system PATH)."""
    try:
        from static_ffmpeg.run import get_or_fetch_platform_executables_else_raise
    except ImportError as exc:
        raise RuntimeError(
            "static-ffmpeg is required for HLS remux. "
            "Install it with: pip install static-ffmpeg"
        ) from exc
    ffmpeg_path, _ = get_or_fetch_platform_executables_else_raise()
    return ffmpeg_path


def remux_segments(tmp_dir: Path, segments: list[Path], dest_path: Path) -> None:
    """Concatenate .ts segments into a single .mkv using bundled ffmpeg -c copy."""
    concat_file = tmp_dir / "concat.txt"
    with open(concat_file, "w") as f:
        for seg in segments:
            f.write(f"file '{seg.resolve()}'\n")

    cmd = [
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "warning",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(dest_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg remux failed:\n{result.stderr}")
