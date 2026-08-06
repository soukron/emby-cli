"""Shared download dispatch and skip/throttle helpers."""

from __future__ import annotations

from pathlib import Path

from emby_cli.client import EmbyClient
from emby_cli.util import (
    format_duration,
    format_size,
    item_duration_seconds,
    item_playback_rate,
    should_skip,
    should_skip_hls,
)

def resolve_rate(item: dict, throttle: float) -> float | None:
    if not throttle:
        return None
    rate = item_playback_rate(item)
    if rate:
        rate *= throttle
        duration = item_duration_seconds(item)
        effective = format_duration(duration / throttle if duration else None)
        print(f"  Throttle: {format_size(rate)}/s x{throttle:.2g} (ETA: {effective})")
    return rate


def do_download(client: EmbyClient, item_id: str, item: dict, dest: Path,
                  method: str, throttle: float) -> None:
    """Dispatch a single item download to the right method."""
    if method == "hls":
        client.download_item_hls(item_id, dest, throttle=throttle)
        return
    rate = resolve_rate(item, throttle)
    if method == "stream":
        client.download_item_stream(item_id, dest, rate_bps=rate)
    else:
        client.download_item(item_id, dest, rate_bps=rate)


def should_skip_item(item: dict, dest: Path, method: str, force: bool) -> bool:
    if force:
        return False
    if method == "hls":
        return should_skip_hls(dest)
    return should_skip(item, dest)
