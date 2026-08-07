"""play command — stream URL in an external player."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import requests

from emby_cli.client import EmbyClient
from emby_cli.mode_args import resolve_query
from emby_cli.output import print_error
from emby_cli.resolve import (
    classify_resolution,
    item_video_width,
    resolve_title_item,
)

_MAC_PLAYER_BINS = (
    "/Applications/VLC.app/Contents/MacOS/VLC",
    "/Applications/IINA.app/Contents/MacOS/IINA",
    "/Applications/mpv.app/Contents/MacOS/mpv",
)


def find_player(explicit: str | None = None) -> list[str]:
    """Resolve an external player command argv, or raise RuntimeError."""
    if explicit:
        cmd = shlex.split(explicit)
        if not cmd:
            raise RuntimeError("Empty --player / EMBY_PLAYER value")
        binary = cmd[0]
        if os.path.sep in binary or binary.startswith("."):
            if not Path(binary).is_file():
                raise RuntimeError(f"Player not found: {binary}")
        elif shutil.which(binary) is None:
            raise RuntimeError(
                f"Player '{binary}' not found in PATH. "
                "Pass a full path via --player or EMBY_PLAYER."
            )
        return cmd

    for name in ("vlc", "mpv", "iina"):
        found = shutil.which(name)
        if found:
            return [found]

    if sys.platform == "darwin":
        for path in _MAC_PLAYER_BINS:
            if Path(path).is_file():
                return [path]

    raise RuntimeError(
        "No external player found (tried vlc, mpv, iina). "
        "Install one or set --player / EMBY_PLAYER to its path, e.g.\n"
        "  --player /Applications/VLC.app/Contents/MacOS/VLC"
    )


def play_url(player_cmd: list[str], url: str, *, wait: bool = False) -> int:
    """Launch *player_cmd* with *url*.

    By default detaches so closing the player window (common on macOS) does not
    leave this process blocked. Pass wait=True to block until the player exits.
    """
    if wait:
        return subprocess.run([*player_cmd, url], check=False).returncode

    subprocess.Popen(
        [*player_cmd, url],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return 0


def validate_play_args(args: argparse.Namespace) -> str | None:
    """Return an error message if selectors are invalid; else ``None``."""
    query, err = resolve_query(args)
    if err:
        return err
    item_id = (getattr(args, "id", None) or "").strip() or None
    if not item_id and not query:
        item_id = (os.environ.get("EMBY_ITEM_ID") or "").strip() or None
    pick_best = bool(getattr(args, "pick_best_item", False))

    if bool(item_id) == bool(query):
        return "Provide exactly one of --id or QUERY/--search"
    if item_id and pick_best:
        return "--pick-best-item can only be used with QUERY/--search"
    return None


def _play_one(
    client: EmbyClient,
    item: dict,
    player_cmd: list[str],
    *,
    wait: bool,
    idx: int | None = None,
    total: int | None = None,
) -> int:
    """Play one resolved item. Return player exit code (0 on detach success)."""
    item_id = item["Id"]
    res = classify_resolution(item_video_width(item))
    year = item.get("ProductionYear", "?")
    prefix = f"[{idx}/{total}] " if idx is not None and total is not None else ""
    print()
    print(f"{prefix}Playing: {item.get('Name')} ({year}) [{item.get('Type')}, {res}]")
    try:
        url = client.resolve_direct_stream_url(item_id)
    except (requests.RequestException, RuntimeError) as exc:
        print_error(f"resolving stream URL: {exc}", idx=idx, total=total)
        return 1

    return play_url(player_cmd, url, wait=wait)


def cmd_play(client: EmbyClient, args: argparse.Namespace) -> None:
    """Resolve DirectStreamUrl and open it in an external player."""
    err = validate_play_args(args)
    if err:
        print(err)
        sys.exit(1)

    query, _ = resolve_query(args)
    item_id = (getattr(args, "id", None) or "").strip() or None
    if not item_id and not query:
        item_id = (os.environ.get("EMBY_ITEM_ID") or "").strip() or None
    pick_best = bool(getattr(args, "pick_best_item", False))
    wait = bool(getattr(args, "wait", False))

    try:
        player_cmd = find_player(getattr(args, "player", None))
    except RuntimeError as exc:
        print_error(str(exc))
        sys.exit(1)

    if item_id:
        item_ids = [x.strip() for x in item_id.split(",") if x.strip()]
        total = len(item_ids)
        errors = 0
        last_rc = 0
        for idx, iid in enumerate(item_ids, 1):
            try:
                item = client.get_item_info(iid)
            except (requests.RequestException, RuntimeError) as exc:
                print_error(f"fetching item {iid}: {exc}", idx=idx, total=total)
                errors += 1
                continue
            rc = _play_one(
                client,
                item,
                player_cmd,
                wait=wait,
                idx=idx if total > 1 else None,
                total=total if total > 1 else None,
            )
            if rc != 0:
                errors += 1
                last_rc = rc
        if errors:
            sys.exit(last_rc if last_rc else 1)
        return

    item = resolve_title_item(client, query, pick_best=pick_best)
    if item is None:
        sys.exit(1)
    rc = _play_one(client, item, player_cmd, wait=wait)
    if rc != 0:
        sys.exit(rc)
