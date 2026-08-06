"""Shared download dispatch, skip/throttle, and library loops."""

from __future__ import annotations

from pathlib import Path

from emby_cli.client import EmbyClient
from emby_cli.constants import DOWNLOADABLE_TYPES
from emby_cli.output import Stats, print_download, print_error, print_section, print_skip
from emby_cli.resolve import item_label
from emby_cli.util import (
    build_dest_path,
    format_duration,
    format_size,
    item_duration_seconds,
    item_playback_rate,
    item_remote_size,
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


def do_download(
    client: EmbyClient,
    item_id: str,
    item: dict,
    dest: Path,
    method: str,
    throttle: float,
) -> None:
    """Dispatch a single item download to the right method."""
    expected = item_remote_size(item)
    if method == "hls":
        client.download_item_hls(item_id, dest, throttle=throttle)
        return
    rate = resolve_rate(item, throttle)
    if method == "stream":
        client.download_item_stream(
            item_id, dest, rate_bps=rate, expected_size=expected
        )
    else:
        client.download_item(item_id, dest, rate_bps=rate, expected_size=expected)


def should_skip_item(item: dict, dest: Path, method: str, force: bool) -> bool:
    if force:
        return False
    if method == "hls":
        return should_skip_hls(dest)
    return should_skip(item, dest)


def download_one_item(
    client: EmbyClient,
    item: dict,
    output: Path,
    *,
    method: str,
    force: bool,
    throttle: float,
    idx: int | None = None,
    total: int | None = None,
    dry_run: bool = False,
) -> str:
    """Download one item. Returns 'ok' | 'skip' | 'error' | 'dry_run'."""
    item_id = item["Id"]
    label = item_label(item)
    dest = build_dest_path(item, output)

    if dry_run:
        print(f"{f'[{idx}/{total}] ' if idx and total else ''}dry-run: {label} -> {dest}")
        return "dry_run"

    if should_skip_item(item, dest, method, force):
        print_skip(label, dest, idx=idx, total=total)
        return "skip"

    print_download(label, dest, method=method, idx=idx, total=total)
    try:
        do_download(client, item_id, item, dest, method, throttle)
        return "ok"
    except Exception as exc:
        print_error(str(exc), idx=idx, total=total)
        return "error"


def download_library_items(
    client: EmbyClient,
    library: dict,
    output: Path,
    *,
    method: str,
    force: bool,
    throttle: float,
    show_section: bool = True,
) -> Stats:
    """Download all downloadable items in one library view."""
    stats = Stats()
    if show_section:
        print_section(f"Library: {library['Name']}")

    items = client.get_all_items(parent_id=library["Id"])
    targets = [i for i in items if i.get("Type") in DOWNLOADABLE_TYPES]
    print(f"Found {len(targets)} items in '{library['Name']}'")

    for idx, item in enumerate(targets, 1):
        result = download_one_item(
            client,
            item,
            output,
            method=method,
            force=force,
            throttle=throttle,
            idx=idx,
            total=len(targets),
        )
        if result == "ok":
            stats.ok += 1
        elif result == "skip":
            stats.skip += 1
        elif result == "error":
            stats.error += 1

    return stats
