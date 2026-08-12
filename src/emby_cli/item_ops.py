"""Resolution, listing, and playback helpers for playable media items."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import SEARCH_ITEM_TYPES, SHOW_ITEM_FIELDS
from emby_cli.media_sort import sort_media_items
from emby_cli.output import Stats, print_done, print_download, print_error, print_skip
from emby_cli.resolve import (
    classify_resolution,
    item_label,
    item_video_width,
    parse_title_line,
    resolve_title_items,
    sort_for_display,
)
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


ListingDefault = Literal["catalog", "parent"]


@dataclass(frozen=True)
class ItemListingQuery:
    """Parameters for a server-side item listing request."""

    query: str = ""
    title_line: str | None = None
    parent_id: str | None = None
    item_types: str = SEARCH_ITEM_TYPES
    year: int | None = None
    api_limit: int | None = None
    order_by: str | None = None
    desc: bool = False
    when_unsorted: ListingDefault = "catalog"
    strict_name: bool = True


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


def split_listing_search_query(
    query: str,
    *,
    year: int | None = None,
) -> tuple[str, int | None]:
    """Map title-line QUERY syntax to Emby ``SearchTerm`` + ``Years`` filter."""
    text = query.strip()
    if not text:
        return "", year
    title, season, episode, parsed_year = parse_title_line(text)
    if season is not None or episode is not None:
        return title, year
    if parsed_year is None:
        return text, year
    return title, year if year is not None else parsed_year


_STRICT_EPISODE_CODE_RE = re.compile(r"^S(\d+)E(\d+)$", re.IGNORECASE)


def emby_search_term_for_strict_query(query: str) -> str:
    """Pick an Emby ``SearchTerm`` that recalls candidates for strict name filtering."""
    text = query.strip()
    if not text:
        return text
    tokens = text.split()
    text_tokens = [token for token in tokens if not _STRICT_EPISODE_CODE_RE.match(token)]
    if text_tokens:
        return max(text_tokens, key=len)
    return text


def matches_strict_name_query(item: dict, query: str) -> bool:
    """Return whether *query* matches the item's display or raw name (case-insensitive)."""
    needle = query.strip().casefold()
    if not needle:
        return True

    label = item_label(item).casefold()
    raw_name = str(item.get("Name") or "").casefold()
    haystacks = {label, raw_name}

    if len(query.split()) == 1 and _STRICT_EPISODE_CODE_RE.match(query.strip()):
        return any(
            haystack == needle or haystack.startswith(f"{needle} ")
            for haystack in haystacks
            if haystack
        )

    return any(needle in haystack for haystack in haystacks if haystack)


def search_strict_name_items(
    client: EmbyClient,
    listing: ItemListingQuery,
    *,
    use_cache: bool = True,
) -> list[dict]:
    """Fetch catalog rows from Emby, then keep only strict display-name matches."""
    emby_term = emby_search_term_for_strict_query(listing.query)
    items, _total = client.items.list_items(
        query=emby_term,
        parent_id=listing.parent_id,
        item_types=listing.item_types,
        year=listing.year,
        limit=None,
        sort_by=listing.order_by,
        desc=listing.desc,
        when_unsorted=listing.when_unsorted,
        use_cache=use_cache,
    )
    return [item for item in items if matches_strict_name_query(item, listing.query)]


def _listing_includes_episodes(item_types: str) -> bool:
    return "Episode" in {part.strip() for part in item_types.split(",") if part.strip()}


def episodes_for_title_line(
    client: EmbyClient,
    title_line: str,
    *,
    year: int | None = None,
    item_types: str = SEARCH_ITEM_TYPES,
) -> list[dict]:
    """Resolve ``Series Sxx[Eyy]`` syntax to episode rows for listings."""
    title, season, episode, parsed_year = parse_title_line(title_line.strip())
    if season is None or not _listing_includes_episodes(item_types):
        return []

    effective_year = year if year is not None else parsed_year
    series_results = client.search_items(title, item_types="Series")
    if not series_results:
        return []

    candidates = series_results
    if effective_year is not None:
        year_matches = [
            series for series in series_results if series.get("ProductionYear") == effective_year
        ]
        if not year_matches:
            return []
        candidates = year_matches

    episodes: list[dict] = []
    for series in candidates:
        rows = client.get_show_episodes(series["Id"], season=season)
        if episode is not None:
            rows = [row for row in rows if row.get("IndexNumber") == episode]
        series_name = series.get("Name")
        for row in rows:
            enriched = dict(row)
            if series_name and not enriched.get("SeriesName"):
                enriched["SeriesName"] = series_name
            episodes.append(enriched)
    return episodes


def _apply_listing_sort_and_limit(
    items: list[dict],
    listing: ItemListingQuery,
) -> tuple[list[dict], int]:
    if listing.order_by:
        ordered = sort_media_items(items, listing.order_by, desc=listing.desc)
    else:
        ordered = sort_for_display(items)
    total = len(ordered)
    if listing.api_limit is not None:
        ordered = ordered[: listing.api_limit]
    return ordered, total


def build_item_listing_query(
    *,
    query: str = "",
    parent_id: str | None = None,
    raw_type: str | None = None,
    year: int | None = None,
    count: int | None = None,
    order_by: str | None = None,
    desc: bool = False,
    when_unsorted: ListingDefault = "catalog",
    parse_query: bool = False,
) -> ItemListingQuery:
    """Build a listing query delegated to Emby (filters, sort, pagination)."""
    text = query.strip()
    if not parse_query:
        return ItemListingQuery(
            query=text,
            parent_id=parent_id,
            item_types=item_types_for_api(raw_type),
            year=year,
            api_limit=None if count is None else count,
            order_by=order_by,
            desc=desc,
            when_unsorted=when_unsorted,
            strict_name=True,
        )
    title, season, _episode, parsed_year = parse_title_line(text)
    effective_year = year if year is not None else parsed_year
    if season is not None:
        return ItemListingQuery(
            query=title,
            title_line=text,
            parent_id=parent_id,
            item_types=item_types_for_api(raw_type),
            year=effective_year,
            api_limit=None if count is None else count,
            order_by=order_by,
            desc=desc,
            when_unsorted=when_unsorted,
            strict_name=False,
        )
    search_query, effective_year = split_listing_search_query(text, year=year)
    return ItemListingQuery(
        query=search_query,
        parent_id=parent_id,
        item_types=item_types_for_api(raw_type),
        year=effective_year,
        api_limit=None if count is None else count,
        order_by=order_by,
        desc=desc,
        when_unsorted=when_unsorted,
        strict_name=False,
    )


def fetch_item_listing(
    client: EmbyClient,
    listing: ItemListingQuery,
    *,
    use_cache: bool = True,
) -> tuple[list[dict], int]:
    """Fetch item rows from Emby using one listing query builder."""
    if listing.title_line and listing.parent_id is None:
        items = episodes_for_title_line(
            client,
            listing.title_line,
            year=listing.year,
            item_types=listing.item_types,
        )
        return _apply_listing_sort_and_limit(items, listing)
    if listing.query and listing.parent_id is None and listing.strict_name:
        filtered = search_strict_name_items(client, listing, use_cache=use_cache)
        return _apply_listing_sort_and_limit(filtered, listing)
    return client.items.list_items(
        query=listing.query,
        parent_id=listing.parent_id,
        item_types=listing.item_types,
        year=listing.year,
        limit=listing.api_limit,
        sort_by=listing.order_by,
        desc=listing.desc,
        when_unsorted=listing.when_unsorted,
        use_cache=use_cache,
    )


def playable_items_for_parent(
    client: EmbyClient,
    parent_id: str,
    *,
    order_by: str | None = None,
    desc: bool = False,
    use_cache: bool = True,
) -> list[dict]:
    """List playable media under *parent_id*, optionally sorted for play/download."""
    items, _total = fetch_item_listing(
        client,
        ItemListingQuery(
            parent_id=parent_id,
            item_types=SEARCH_ITEM_TYPES,
            order_by=order_by,
            desc=desc,
            when_unsorted="parent",
        ),
        use_cache=use_cache,
    )
    return items


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
    parse_query: bool = False,
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
        if parse_query:
            _title, season, _episode, _parsed_year = parse_title_line(query.strip())
            if season is not None and _listing_includes_episodes(item_types):
                _title, _season, _episode, parsed_year = parse_title_line(query.strip())
                matches = episodes_for_title_line(
                    client,
                    query.strip(),
                    year=parsed_year,
                    item_types=item_types,
                )
            else:
                search_query, search_year = split_listing_search_query(query)
                matches, _total = client.items.search(
                    search_query,
                    item_types=item_types,
                    year=search_year,
                    use_cache=use_cache,
                )
        else:
            listing = ItemListingQuery(
                query=query.strip(),
                item_types=item_types,
                when_unsorted="catalog",
            )
            matches = search_strict_name_items(client, listing, use_cache=use_cache)
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


@dataclass(frozen=True)
class DownloadOpts:
    """Download settings shared by item and library download commands."""

    output: Path
    throttle: float
    method: str
    dry_run: bool
    mirror_path: bool
    path_strip: str | None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> DownloadOpts:
        raw_strip = getattr(args, "path_strip", None)
        return cls(
            output=Path(args.output),
            throttle=float(getattr(args, "throttle", 0) or 0),
            method=getattr(args, "method", "download"),
            dry_run=bool(getattr(args, "dry_run", False)),
            mirror_path=bool(getattr(args, "mirror_path", False)),
            path_strip=(raw_strip.strip() or None) if isinstance(raw_strip, str) else None,
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
    mirror_path: bool = False,
    path_strip: str | None = None,
) -> str:
    """Download one item. Returns 'ok' | 'skip' | 'error' | 'dry_run'."""
    item_id = item["Id"]
    label = item_label(item)
    dest = build_dest_path(item, output, mirror_path=mirror_path, path_strip=path_strip)

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
    except (requests.RequestException, RuntimeError, OSError) as exc:
        print_error(str(exc), idx=idx, total=total)
        return "error"


def download_items(
    client: EmbyClient,
    items: list[dict],
    output: Path,
    *,
    method: str,
    force: bool,
    throttle: float,
    dry_run: bool = False,
    show_single_progress: bool = False,
    mirror_path: bool = False,
    path_strip: str | None = None,
) -> Stats:
    """Download *items* and accumulate their results."""
    stats = Stats()
    total = len(items)
    show_progress = total > 1 or show_single_progress
    for idx, item in enumerate(items, 1):
        result = download_one_item(
            client,
            item,
            output,
            method=method,
            force=force,
            throttle=throttle,
            idx=idx if show_progress else None,
            total=total if show_progress else None,
            dry_run=dry_run,
            mirror_path=mirror_path,
            path_strip=path_strip,
        )
        if result in ("ok", "dry_run"):
            stats.ok += 1
        elif result == "skip":
            stats.skip += 1
        elif result == "error":
            stats.error += 1
    return stats


def download_item_ids(
    client: EmbyClient,
    item_id: str,
    output: Path,
    *,
    method: str,
    force: bool,
    throttle: float,
    dry_run: bool = False,
    raw_type: str | None = None,
    mirror_path: bool = False,
    path_strip: str | None = None,
) -> Stats:
    """Download comma-separated item IDs."""
    item_ids = [part.strip() for part in item_id.split(",") if part.strip()]
    items: list[dict] = []
    stats = Stats()
    total = len(item_ids)
    for idx, iid in enumerate(item_ids, 1):
        try:
            item = client.get_item_info(iid)
        except (requests.RequestException, RuntimeError) as exc:
            print_error(f"fetching item {iid}: {exc}", idx=idx, total=total)
            stats.error += 1
            continue
        if not item_matches_type(item, raw_type):
            print_error(
                f"item id '{iid}' not found",
                idx=idx if total > 1 else None,
                total=total if total > 1 else None,
            )
            stats.error += 1
            continue
        items.append(item)
    if items:
        got = download_items(
            client,
            items,
            output,
            method=method,
            force=force,
            throttle=throttle,
            dry_run=dry_run,
            mirror_path=mirror_path,
            path_strip=path_strip,
        )
        stats.ok += got.ok
        stats.skip += got.skip
        stats.error += got.error
    return stats


def download_from_file(
    client: EmbyClient,
    file_path: Path | str,
    output: Path,
    *,
    method: str,
    force: bool,
    throttle: float,
    dry_run: bool = False,
    pick_best: bool = False,
    mirror_path: bool = False,
    path_strip: str | None = None,
) -> int:
    """Download titles listed in a text file. Returns a process exit code."""
    path = Path(file_path)
    lines: list[str] = []
    with open(path) as handle:
        for raw in handle:
            raw = raw.strip()
            if raw and not raw.startswith("#"):
                lines.append(raw)

    if not lines:
        print("No titles found in file.")
        return 0

    print(f"Loaded {len(lines)} titles from {path}\n")

    line_stats: list[tuple[str, str, float, str]] = []
    totals = Stats()
    total_t0 = time.monotonic()

    for idx, raw_line in enumerate(lines, 1):
        emby_id_match = re.match(r"^embyId=(\S+)$", raw_line.strip(), re.IGNORECASE)
        line_t0 = time.monotonic()

        if emby_id_match:
            item_id = emby_id_match.group(1)
            label = f"embyId={item_id}"
            print(f"\n[{idx}/{len(lines)}] Direct ID: {item_id}")
            try:
                item = client.get_item_info(item_id)
            except (requests.RequestException, RuntimeError) as exc:
                print_error(str(exc))
                elapsed = time.monotonic() - line_t0
                line_stats.append((label, "ERROR", elapsed, str(exc)))
                totals.error += 1
                continue

            result = download_one_item(
                client,
                item,
                output,
                method=method,
                force=force,
                throttle=throttle,
                dry_run=dry_run,
                mirror_path=mirror_path,
                path_strip=path_strip,
            )
            elapsed = time.monotonic() - line_t0
            status_map = {
                "ok": "OK",
                "skip": "SKIPPED",
                "error": "ERROR",
                "dry_run": "DRY RUN",
            }
            status = status_map.get(result, "ERROR")
            line_stats.append((label, status, elapsed, item.get("Name", "")))
            if result == "ok":
                totals.ok += 1
            elif result == "skip":
                totals.skip += 1
            elif result == "error":
                totals.error += 1
            continue

        label = raw_line
        print(f"\n[{idx}/{len(lines)}] {raw_line}")
        items = resolve_title_items(
            client,
            raw_line,
            pick_best=pick_best,
            allow_season_all=True,
        )
        if items is None:
            elapsed = time.monotonic() - line_t0
            line_stats.append((label, "NOT FOUND", elapsed, ""))
            totals.not_found += 1
            continue

        line_ok = line_skip = line_err = 0
        for item in items:
            result = download_one_item(
                client,
                item,
                output,
                method=method,
                force=force,
                throttle=throttle,
                dry_run=dry_run,
                mirror_path=mirror_path,
                path_strip=path_strip,
            )
            if result == "ok":
                line_ok += 1
                totals.ok += 1
            elif result == "skip":
                line_skip += 1
                totals.skip += 1
            elif result == "error":
                line_err += 1
                totals.error += 1

        elapsed = time.monotonic() - line_t0
        if dry_run:
            status = "DRY RUN"
            detail = f"{len(items)} items"
        elif line_err and line_ok:
            status = "PARTIAL"
            detail = f"ok={line_ok} skip={line_skip} error={line_err}"
        elif line_err:
            status = "ERROR"
            detail = f"error={line_err}"
        elif line_ok:
            status = "OK"
            detail = f"{line_ok} items" if len(items) > 1 else ""
        else:
            status = "SKIPPED"
            detail = f"{line_skip} skipped" if line_skip else ""

        line_stats.append((label, status, elapsed, detail))

    totals.elapsed = time.monotonic() - total_t0

    print(f"\n{'=' * 60}")
    print(f"From-file complete in {format_duration(totals.elapsed)}\n")

    max_label = max((len(label) for label, *_rest in line_stats), default=10)
    for label, status, elapsed, detail in line_stats:
        time_str = format_duration(elapsed) if elapsed > 0 else "-"
        detail_str = f" ({detail})" if detail else ""
        dots = "." * (max_label - len(label) + 3)
        print(f"  {label} {dots} {time_str:<10} {status}{detail_str}")

    print_done(totals, label="From-file")
    return totals.exit_code(fail_on_not_found=True)


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
    Player stdout/stderr are always suppressed so VLC/mpv logs do not clutter the CLI.
    """
    popen_kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if wait:
        return subprocess.run(
            [*player_cmd, url],
            check=False,
            **popen_kwargs,
        ).returncode

    subprocess.Popen(
        [*player_cmd, url],
        start_new_session=True,
        **popen_kwargs,
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


def play_items(
    client: EmbyClient,
    items: list[dict],
    player_cmd: list[str],
    *,
    wait: bool = False,
    show_progress: bool = False,
) -> int:
    """Play *items* sequentially. Return process exit code."""
    total = len(items)
    errors = 0
    last_rc = 0
    show_idx = show_progress or total > 1
    for idx, item in enumerate(items, 1):
        rc = play_one_item(
            client,
            item,
            player_cmd,
            wait=wait,
            idx=idx if show_idx else None,
            total=total if show_idx else None,
        )
        if rc != 0:
            errors += 1
            last_rc = rc
    if errors:
        return last_rc if last_rc else 1
    return 0
