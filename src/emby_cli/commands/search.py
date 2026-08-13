"""search command — media items or libraries (--item/--library + QUERY/--id)."""

from __future__ import annotations

import argparse
import sys

import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import SEARCH_COUNT_DEFAULT
from emby_cli.data_cache import load_json, save_json
from emby_cli.deprecation import warn_deprecated
from emby_cli.download_ops import find_library, match_libraries
from emby_cli.item_ops import (
    build_item_listing_query,
    fetch_item_listing,
    item_types_for_api,
)
from emby_cli.mode_args import mode_is_library, resolve_query
from emby_cli.resolve import (
    item_video_width,
    print_available_libraries,
    print_item_choices,
    print_library_choices,
    sort_for_display,
)
from emby_cli.util import item_remote_size


def _print_total(shown: int, available: int | None = None) -> None:
    """Print ``Total: N`` or ``Total: N (out of M)`` when truncated."""
    if available is not None and available > shown:
        print(f"\nTotal: {shown} (out of {available})")
    else:
        print(f"\nTotal: {shown}")
    print()


def _print_libraries(
    client: EmbyClient,
    libraries: list[dict],
    *,
    count: int | None,
    no_cache: bool,
) -> None:
    if not libraries:
        print("No results.")
        return
    available = len(libraries)
    shown = libraries if count is None else libraries[:count]
    rows = _library_rows_cached(
        client,
        shown,
        item_types="Movie,Episode,Audio",
        no_cache=no_cache,
    )
    print_library_choices(rows, sort_rows=False)
    _print_total(len(shown), available)


def _print_library_rows(rows: list[dict], *, count: int | None) -> None:
    if not rows:
        print("No results.")
        return
    available = len(rows)
    shown = rows if count is None else rows[:count]
    print_library_choices(shown, sort_rows=False)
    _print_total(len(shown), available)


def _cache_key_parts(client: EmbyClient) -> tuple[str, str]:
    server = client.server_url.rstrip("/")
    user_id = client.resolve_user_id()
    return server, user_id


def _get_libraries_cached(client: EmbyClient, *, no_cache: bool) -> list[dict]:
    server, user_id = _cache_key_parts(client)
    key = f"v1:libraries:{server}:{user_id}"
    if not no_cache:
        cached = load_json(key)
        if isinstance(cached, list):
            return cached
    libs = client.get_libraries()
    save_json(key, libs)
    return libs


def _library_rows_cached(
    client: EmbyClient,
    libraries: list[dict],
    *,
    item_types: str,
    no_cache: bool,
) -> list[dict]:
    server, user_id = _cache_key_parts(client)
    rows: list[dict] = []
    for lib in libraries:
        lib_id = str(lib.get("Id") or "")
        key = f"v1:library-itemcount:{server}:{user_id}:{item_types}:{lib_id}"
        count_val: int | None = None
        if not no_cache:
            cached = load_json(key)
            if isinstance(cached, int):
                count_val = cached
        if count_val is None:
            page = client.get_items(parent_id=lib_id, item_type=item_types, limit=0)
            count_val = int(page.get("TotalRecordCount") or 0)
            save_json(key, count_val)
        rows.append({
            "Id": lib_id,
            "Name": lib.get("Name") or "?",
            "Type": lib.get("CollectionType") or lib.get("Type") or "Library",
            "ItemCount": count_val,
        })
    return rows


def _item_info_cached(client: EmbyClient, item_id: str, *, no_cache: bool) -> dict:
    server, user_id = _cache_key_parts(client)
    key = f"v1:item-info:{server}:{user_id}:{item_id}"
    if not no_cache:
        cached = load_json(key)
        if isinstance(cached, dict):
            return cached
    item = client.get_item_info(item_id)
    save_json(key, item)
    return item


def _selector_count(args: argparse.Namespace, query: str | None) -> int:
    item_id = (getattr(args, "id", None) or "").strip()
    return sum(bool(x) for x in (item_id, query))


def _opt_str_arg(args: argparse.Namespace, name: str) -> str | None:
    raw = getattr(args, name, None)
    if not isinstance(raw, str):
        return None
    val = raw.strip()
    return val or None


def _opt_int_arg(args: argparse.Namespace, name: str) -> int | None:
    raw = getattr(args, name, None)
    return raw if isinstance(raw, int) else None


def _normalize_item_type(item_type: str | None) -> str | None:
    if not item_type:
        return None
    allowed = {
        "movie": "Movie",
        "episode": "Episode",
        "audio": "Audio",
        "video": "Video",
    }
    return allowed.get(item_type.strip().lower())


def _library_type_value(lib: dict) -> str:
    return str(lib.get("CollectionType") or lib.get("Type") or "").strip().casefold()


def _library_matches_type(lib: dict, raw_type: str | None) -> bool:
    if not raw_type:
        return True
    wanted = raw_type.strip().casefold()
    if not wanted:
        return True
    actual = _library_type_value(lib)
    return wanted == actual


def _parse_count(raw_count: object) -> tuple[int | None, bool]:
    """Return (count, is_all). count=None means unlimited."""
    if raw_count is None:
        return SEARCH_COUNT_DEFAULT, False
    if isinstance(raw_count, int):
        count = raw_count
    else:
        text = str(raw_count).strip().lower()
        if text == "all":
            return None, True
        count = int(text)
    if count < 1:
        raise ValueError("error: --count must be >= 1")
    return count, False


def _sort_key_id(row: dict) -> tuple[int, int, str]:
    iid = str(row.get("Id") or "")
    if iid.isdigit():
        return (0, int(iid), iid)
    return (1, 0, iid.casefold())


def _sort_rows(
    rows: list[dict],
    *,
    sort_by: str | None,
    desc: bool,
    is_library: bool,
) -> list[dict]:
    if not sort_by:
        return sort_for_display(rows)
    if sort_by == "name":
        return sorted(rows, key=lambda r: str(r.get("Name") or "").casefold(), reverse=desc)
    if sort_by == "id":
        return sorted(rows, key=_sort_key_id, reverse=desc)
    if is_library:
        if sort_by == "items":
            return sorted(
                rows,
                key=lambda r: (
                    int(r.get("ItemCount") or -1),
                    str(r.get("Name") or "").casefold(),
                    _sort_key_id(r),
                ),
                reverse=desc,
            )
        return rows
    if sort_by == "year":
        year_rows = [r for r in rows if r.get("ProductionYear") is not None]
        no_year_rows = [r for r in rows if r.get("ProductionYear") is None]
        year_rows = sorted(
            year_rows,
            key=lambda r: (
                int(r.get("ProductionYear") or 0),
                str(r.get("Name") or "").casefold(),
                _sort_key_id(r),
            ),
            reverse=desc,
        )
        return year_rows + no_year_rows
    if sort_by == "size":
        with_size = [r for r in rows if item_remote_size(r) is not None]
        without_size = [r for r in rows if item_remote_size(r) is None]
        with_size = sorted(
            with_size,
            key=lambda r: (
                int(item_remote_size(r) or 0),
                str(r.get("Name") or "").casefold(),
                _sort_key_id(r),
            ),
            reverse=desc,
        )
        return with_size + without_size
    # sort_by == "resolution"
    with_res = [r for r in rows if item_video_width(r) is not None]
    without_res = [r for r in rows if item_video_width(r) is None]
    with_res = sorted(
        with_res,
        key=lambda r: (
            int(item_video_width(r) or 0),
            str(r.get("Name") or "").casefold(),
            _sort_key_id(r),
        ),
        reverse=desc,
    )
    return with_res + without_res


def _sort_library_rows_by_items(rows: list[dict], *, desc: bool) -> list[dict]:
    return sorted(
        rows,
        key=lambda r: (
            int(r.get("ItemCount") or -1),
            str(r.get("Name") or "").casefold(),
            _sort_key_id(r),
        ),
        reverse=desc,
    )


def validate_search_args(args: argparse.Namespace) -> str | None:
    """Return an error message if selectors are invalid; else ``None``."""
    raw_count = getattr(args, "count", SEARCH_COUNT_DEFAULT)
    try:
        _count, count_all = _parse_count(raw_count)
    except ValueError as exc:
        return str(exc)
    query, err = resolve_query(args)
    if err:
        return err
    selectors = _selector_count(args, query)
    if mode_is_library(args) and selectors == 0:
        pass
    elif selectors == 0 and not count_all:
        return (
            "Provide QUERY/--search or --id. "
            "Use --count all to list everything."
        )
    if selectors > 1:
        return (
            "Provide exactly one of QUERY on --item/--library, "
            "--search, or --id"
        )
    item_type_raw = _opt_str_arg(args, "item_type")
    year = _opt_int_arg(args, "year")
    sort_by = _opt_str_arg(args, "order_by")
    if mode_is_library(args) and year is not None:
        return "--year can only be used with --item/--media-item"
    if mode_is_library(args) and sort_by in {
        "year", "size", "resolution", "release-date", "added",
    }:
        return "--order-by year/size/resolution/release-date/added can only be used with --item/--media-item"
    if not mode_is_library(args) and sort_by == "items":
        return "--order-by items can only be used with --library"
    if (not mode_is_library(args)) and getattr(args, "id", None) and (item_type_raw or year is not None):
        return "--type/--year cannot be used with --id"
    if (not mode_is_library(args)) and item_type_raw and _normalize_item_type(item_type_raw) is None:
        return "error: --type must be one of Movie, Episode, Audio, Video"
    if year is not None and year < 0:
        return "error: --year must be >= 0"
    return None


def cmd_search(client: EmbyClient, args: argparse.Namespace) -> None:
    warn_deprecated("search")
    err = validate_search_args(args)
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)

    raw_count = getattr(args, "count", SEARCH_COUNT_DEFAULT)
    count, count_all = _parse_count(raw_count)
    item_id = (getattr(args, "id", None) or "").strip() or None
    query, _ = resolve_query(args)
    item_type_raw = _opt_str_arg(args, "item_type")
    year = _opt_int_arg(args, "year")
    sort_by = _opt_str_arg(args, "order_by")
    desc = getattr(args, "desc", False) is True
    no_cache = getattr(args, "no_cache", False) is True
    client.no_data_cache = no_cache

    if mode_is_library(args):
        libraries = _get_libraries_cached(client, no_cache=no_cache)
        libraries = [lib for lib in libraries if _library_matches_type(lib, item_type_raw)]
        if item_id:
            lib = find_library(libraries, library_id=item_id)
            if not lib:
                print(f"Library id '{item_id}' not found. Available:")
                print_available_libraries(libraries)
                sys.exit(1)
            ordered = _sort_rows([lib], sort_by=sort_by, desc=desc, is_library=True)
            _print_libraries(client, ordered, count=count, no_cache=no_cache)
            return

        matches = match_libraries(libraries, query or "")
        listing = libraries if count_all and not query else matches
        if sort_by == "items":
            rows = _library_rows_cached(
                client,
                listing,
                item_types="Movie,Episode,Audio",
                no_cache=no_cache,
            )
            ordered_rows = _sort_library_rows_by_items(rows, desc=desc)
            _print_library_rows(ordered_rows, count=count)
            return
        ordered = _sort_rows(listing, sort_by=sort_by, desc=desc, is_library=True)
        _print_libraries(client, ordered, count=count, no_cache=no_cache)
        return

    # --item / --media-item
    if item_id:
        try:
            item = _item_info_cached(client, item_id, no_cache=no_cache)
        except (requests.RequestException, RuntimeError) as exc:
            print(f"error: fetching item {item_id}: {exc}", file=sys.stderr)
            sys.exit(1)
        print_item_choices([item])
        _print_total(1)
        return

    search_query = query or ""
    if sort_by in {"size", "resolution"}:
        items, _total = client.items.search(
            search_query,
            item_types=item_types_for_api(item_type_raw),
            year=year,
            limit=None,
            sort_by=None,
            desc=False,
            use_cache=not no_cache,
        )
        ordered = _sort_rows(items, sort_by=sort_by, desc=desc, is_library=False)
        shown = ordered if count is None else ordered[:count]
        available = len(ordered)
    else:
        listing = build_item_listing_query(
            query=search_query,
            raw_type=item_type_raw,
            year=year,
            count=count,
            order_by=sort_by,
            desc=desc,
        )
        shown, available = fetch_item_listing(
            client,
            listing,
            use_cache=not no_cache,
        )
    if not shown:
        print("No results.")
        return
    print_item_choices(shown, sort_rows=False)
    _print_total(len(shown), available if available > len(shown) else None)
