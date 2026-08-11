"""search command — media items or libraries (--item/--library + QUERY/--id)."""

from __future__ import annotations

import argparse
import sys

import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import SEARCH_COUNT_DEFAULT, SEARCH_ITEM_TYPES
from emby_cli.download_ops import find_library, library_rows, match_libraries
from emby_cli.mode_args import mode_is_library, resolve_query
from emby_cli.resolve import (
    print_available_libraries,
    print_item_choices,
    print_library_choices,
    sort_for_display,
)


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
) -> None:
    if not libraries:
        print("No results.")
        return
    available = len(libraries)
    shown = sort_for_display(libraries) if count is None else sort_for_display(libraries)[:count]
    print_library_choices(library_rows(client, shown))
    _print_total(len(shown), available)


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
    if selectors == 0 and not count_all:
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
    if mode_is_library(args) and (item_type_raw or year is not None):
        return "--type/--year can only be used with --item/--media-item"
    if getattr(args, "id", None) and (item_type_raw or year is not None):
        return "--type/--year cannot be used with --id"
    if item_type_raw and _normalize_item_type(item_type_raw) is None:
        return "error: --type must be one of Movie, Episode, Audio, Video"
    if year is not None and year < 0:
        return "error: --year must be >= 0"
    return None


def _item_matches_filters(item: dict, *, item_type: str | None, year: int | None) -> bool:
    if item_type and item.get("Type") != item_type:
        return False
    if year is not None and item.get("ProductionYear") != year:
        return False
    return True


def _apply_item_filters(items: list[dict], *, item_type: str | None, year: int | None) -> list[dict]:
    if not item_type and year is None:
        return items
    return [it for it in items if _item_matches_filters(it, item_type=item_type, year=year)]


def cmd_search(client: EmbyClient, args: argparse.Namespace) -> None:
    err = validate_search_args(args)
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)

    raw_count = getattr(args, "count", SEARCH_COUNT_DEFAULT)
    count, count_all = _parse_count(raw_count)
    item_id = (getattr(args, "id", None) or "").strip() or None
    query, _ = resolve_query(args)
    item_type = _normalize_item_type(_opt_str_arg(args, "item_type"))
    year = _opt_int_arg(args, "year")

    if mode_is_library(args):
        libraries = client.get_libraries()
        if item_id:
            lib = find_library(libraries, library_id=item_id)
            if not lib:
                print(f"Library id '{item_id}' not found. Available:")
                print_available_libraries(libraries)
                sys.exit(1)
            _print_libraries(client, [lib], count=count)
            return

        matches = match_libraries(libraries, query or "")
        listing = libraries if count_all and not query else matches
        _print_libraries(client, listing, count=count)
        return

    # --item / --media-item
    if item_id:
        try:
            item = client.get_item_info(item_id)
        except (requests.RequestException, RuntimeError) as exc:
            print(f"error: fetching item {item_id}: {exc}", file=sys.stderr)
            sys.exit(1)
        print_item_choices([item])
        _print_total(1)
        return

    search_query = query or ""
    items, _available = client.search_items_result(
        search_query,
        item_types=item_type or SEARCH_ITEM_TYPES,
        limit=None,
    )
    filtered = _apply_item_filters(items, item_type=item_type, year=year)
    shown = filtered if count is None else filtered[:count]
    filtered_total = len(filtered)
    if not shown:
        print("No results.")
        return
    print_item_choices(shown)
    _print_total(len(shown), filtered_total)
