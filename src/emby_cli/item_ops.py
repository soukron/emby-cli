"""Resolution, listing, and playback helpers for playable media items."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import SEARCH_ITEM_TYPES, SHOW_ITEM_FIELDS
from emby_cli.output import print_error
from emby_cli.resolve import classify_resolution, item_video_width

ITEM_TYPE_ALIASES: dict[str, str] = {
    "movie": "Movie",
    "movies": "Movie",
    "episode": "Episode",
    "episodes": "Episode",
    "audio": "Audio",
    "music": "Audio",
    "video": "Video",
    "videos": "Video",
}


class ItemResolutionError(ValueError):
    """A media item selector was missing, not found, or ambiguous."""

    def __init__(self, message: str, matches: list[dict] | None = None):
        super().__init__(message)
        self.matches = matches or []


@dataclass(frozen=True)
class ItemListingQuery:
    """Parameters for a server-side item listing request."""

    query: str
    item_types: str
    year: int | None
    api_limit: int | None
    api_sort: str | None
    desc: bool


def item_selector_id(args: object) -> str | None:
    """Return an item ID from parent ``--id`` or subcommand ``--id``."""
    for name in ("id", "item_id"):
        value = getattr(args, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def normalize_item_type(raw_type: str | None) -> str | None:
    if not raw_type:
        return None
    return ITEM_TYPE_ALIASES.get(raw_type.strip().casefold())


def item_types_for_api(raw_type: str | None) -> str:
    normalized = normalize_item_type(raw_type)
    return normalized or SEARCH_ITEM_TYPES


def item_matches_type(item: dict, raw_type: str | None) -> bool:
    normalized = normalize_item_type(raw_type)
    if not normalized:
        return True
    return item.get("Type") == normalized


def build_item_listing_query(
    *,
    query: str = "",
    raw_type: str | None = None,
    year: int | None = None,
    count: int | None = None,
    order_by: str | None = None,
    desc: bool = False,
) -> ItemListingQuery:
    """Build a listing query delegated to Emby (filters, sort, pagination)."""
    return ItemListingQuery(
        query=query,
        item_types=item_types_for_api(raw_type),
        year=year,
        api_limit=None if count is None else count,
        api_sort=order_by,
        desc=desc,
    )


def fetch_item_listing(
    client: EmbyClient,
    listing: ItemListingQuery,
    *,
    use_cache: bool = True,
) -> tuple[list[dict], int]:
    """Fetch one item listing page from Emby."""
    items, total = client.items.search(
        listing.query,
        item_types=listing.item_types,
        year=listing.year,
        limit=listing.api_limit,
        sort_by=listing.api_sort,
        desc=listing.desc,
        use_cache=use_cache,
    )
    return items, total


def _id_matches(items: list[dict], item_id: str) -> list[dict]:
    needle = item_id.strip().casefold()
    exact = [item for item in items if str(item.get("Id") or "").casefold() == needle]
    if exact:
        return exact
    return [
        item
        for item in items
        if str(item.get("Id") or "").casefold().startswith(needle)
    ]


def resolve_item(
    client: EmbyClient,
    *,
    query: str | None = None,
    item_id: str | None = None,
    raw_type: str | None = None,
    use_cache: bool = True,
) -> dict:
    """Resolve one media item or raise an error carrying candidate rows."""
    item_types = item_types_for_api(raw_type)
    if item_id:
        try:
            item = client.items.get(
                item_id,
                fields=SHOW_ITEM_FIELDS,
                use_cache=use_cache,
            )
            if item_matches_type(item, raw_type):
                return item
            raise ItemResolutionError(f"item id '{item_id}' not found")
        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            if response is None or response.status_code != 404:
                raise
        catalog, _total = client.items.search(
            "",
            item_types=item_types,
            use_cache=use_cache,
        )
        matches = _id_matches(catalog, item_id)
        selector = f"id '{item_id}'"
    elif query:
        matches, _total = client.items.search(
            query,
            item_types=item_types,
            use_cache=use_cache,
        )
        selector = f"query '{query}'"
    else:
        raise ItemResolutionError("provide a media item QUERY or --id")

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ItemResolutionError(f"item {selector} not found")
    raise ItemResolutionError(
        f"item {selector} is ambiguous; use --id",
        matches,
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


def play_one_item(
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


def play_item_ids(
    client: EmbyClient,
    item_id: str,
    player_cmd: list[str],
    *,
    raw_type: str | None = None,
    wait: bool = False,
) -> int:
    """Play comma-separated item IDs. Return process exit code."""
    item_ids = [part.strip() for part in item_id.split(",") if part.strip()]
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
        if not item_matches_type(item, raw_type):
            print_error(
                f"item id '{iid}' not found",
                idx=idx if total > 1 else None,
                total=total if total > 1 else None,
            )
            errors += 1
            continue
        rc = play_one_item(
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
        return last_rc if last_rc else 1
    return 0
