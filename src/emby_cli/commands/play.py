"""play command — stream URL in an external player."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from emby_cli.client import EmbyClient
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


def redact_url(url: str) -> str:
    return re.sub(r"(api_key=)[^&]+", r"\1***", url, flags=re.I)

def cmd_play(client: EmbyClient, args: argparse.Namespace) -> None:
    """Resolve DirectStreamUrl and open it in an external player."""
    item_id = (args.item_id or "").strip() or None
    query = (args.query or "").strip() or None

    if not item_id and not query:
        print("Specify --item-id or a search query "
              "(e.g. 'Movie (2010)' or 'Show S01E01')")
        sys.exit(1)

    if item_id:
        try:
            item = client.get_item_info(item_id)
        except Exception as exc:
            print_error(f"fetching item {item_id}: {exc}")
            sys.exit(1)
    else:
        pick_best = bool(getattr(args, "pick_best_item", 0))
        item = resolve_title_item(client, query, pick_best=pick_best)
        if item is None:
            sys.exit(1)
        item_id = item["Id"]

    try:
        player_cmd = find_player(getattr(args, "player", None))
    except RuntimeError as exc:
        print_error(str(exc))
        sys.exit(1)

    res = classify_resolution(item_video_width(item))
    year = item.get("ProductionYear", "?")
    print(f"Playing: {item.get('Name')} ({year}) [{item.get('Type')}, {res}]")
    try:
        url = client.resolve_direct_stream_url(item_id)
    except Exception as exc:
        print_error(f"resolving stream URL: {exc}")
        sys.exit(1)

    print(f"Stream:  {redact_url(url)}")
    print(f"Player:  {' '.join(player_cmd)}")
    wait = bool(getattr(args, "wait", False))
    rc = play_url(player_cmd, url, wait=wait)
    if not wait:
        print("Launched (detached). Use --wait to block until the player exits.")
    if rc != 0:
        sys.exit(rc)
