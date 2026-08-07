"""search command — media items or libraries (--item/--library + QUERY/--id/--all)."""

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
    count: int,
) -> None:
    if not libraries:
        print("No results.")
        return
    available = len(libraries)
    shown = sort_for_display(libraries)[:count]
    print_library_choices(library_rows(client, shown))
    _print_total(len(shown), available)


def _selector_count(args: argparse.Namespace, query: str | None) -> int:
    item_id = (getattr(args, "id", None) or "").strip()
    use_all = bool(getattr(args, "all", False))
    return sum(bool(x) for x in (item_id, query, use_all))


def validate_search_args(args: argparse.Namespace) -> str | None:
    """Return an error message if selectors are invalid; else ``None``."""
    raw_count = getattr(args, "count", SEARCH_COUNT_DEFAULT)
    count = SEARCH_COUNT_DEFAULT if raw_count is None else int(raw_count)
    if count < 1:
        return "error: --count must be >= 1"
    query, err = resolve_query(args)
    if err:
        return err
    if _selector_count(args, query) != 1:
        return (
            "Provide exactly one of QUERY on --item/--library, "
            "--search, --id, or --all"
        )
    return None


def cmd_search(client: EmbyClient, args: argparse.Namespace) -> None:
    err = validate_search_args(args)
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)

    raw_count = getattr(args, "count", SEARCH_COUNT_DEFAULT)
    count = SEARCH_COUNT_DEFAULT if raw_count is None else int(raw_count)
    item_id = (getattr(args, "id", None) or "").strip() or None
    query, _ = resolve_query(args)
    use_all = bool(getattr(args, "all", False))

    if mode_is_library(args):
        libraries = client.get_libraries()
        if use_all:
            _print_libraries(client, libraries, count=count)
            return
        if item_id:
            lib = find_library(libraries, library_id=item_id)
            if not lib:
                print(f"Library id '{item_id}' not found. Available:")
                print_available_libraries(libraries)
                sys.exit(1)
            _print_libraries(client, [lib], count=count)
            return

        matches = match_libraries(libraries, query or "")
        _print_libraries(client, matches, count=count)
        return

    # --item / --media-item
    if use_all:
        probe = client.get_items(item_type=SEARCH_ITEM_TYPES, limit=0)
        total = int(probe.get("TotalRecordCount") or 0)
        if total > count:
            print(
                f"There are {total} media items on this server. "
                "Please narrow the results with a query, for example:\n"
                '  emby-cli search --item "title"',
                file=sys.stderr,
            )
            sys.exit(1)
        if total == 0:
            print("No results.")
            return
        items = client.get_all_items(item_type=SEARCH_ITEM_TYPES)
        print_item_choices(items)
        _print_total(len(items))
        return

    if item_id:
        try:
            item = client.get_item_info(item_id)
        except (requests.RequestException, RuntimeError) as exc:
            print(f"error: fetching item {item_id}: {exc}", file=sys.stderr)
            sys.exit(1)
        print_item_choices([item])
        _print_total(1)
        return

    items, available = client.search_items_result(
        query,
        item_types=SEARCH_ITEM_TYPES,
        limit=count,
    )
    if not items:
        print("No results.")
        return
    print_item_choices(items)
    _print_total(len(items), available)
