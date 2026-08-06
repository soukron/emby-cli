"""search command — media items or libraries (--media-item/--library + --id/--search/--all)."""

from __future__ import annotations

import argparse
import sys

from emby_cli.client import EmbyClient
from emby_cli.constants import SEARCH_COUNT_DEFAULT, SEARCH_ITEM_TYPES
from emby_cli.download_ops import find_library
from emby_cli.resolve import print_item_choices, print_library_choices


def _library_rows(client: EmbyClient, libraries: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for lib in libraries:
        page = client.get_items(parent_id=lib["Id"], limit=0)
        rows.append({
            "Id": lib.get("Id", ""),
            "Name": lib.get("Name") or "?",
            "Type": lib.get("CollectionType") or lib.get("Type") or "Library",
            "ItemCount": page.get("TotalRecordCount", 0),
        })
    return rows


def _print_libraries(
    client: EmbyClient,
    libraries: list[dict],
    *,
    count: int,
) -> None:
    if not libraries:
        print("No results.")
        return
    shown = libraries[:count]
    print_library_choices(_library_rows(client, shown))
    print(f"\nTotal: {len(shown)}")
    print()


def _selector_count(args: argparse.Namespace) -> int:
    item_id = (getattr(args, "id", None) or "").strip()
    query = (getattr(args, "search", None) or "").strip()
    use_all = bool(getattr(args, "all", False))
    return sum(bool(x) for x in (item_id, query, use_all))


def cmd_search(client: EmbyClient, args: argparse.Namespace) -> None:
    count = int(getattr(args, "count", SEARCH_COUNT_DEFAULT) or SEARCH_COUNT_DEFAULT)
    if count < 1:
        print("error: --count must be >= 1", file=sys.stderr)
        sys.exit(1)

    item_id = (getattr(args, "id", None) or "").strip() or None
    query = (getattr(args, "search", None) or "").strip() or None
    use_all = bool(getattr(args, "all", False))

    if _selector_count(args) != 1:
        print("Provide exactly one of --id, --search, or --all")
        sys.exit(1)

    if getattr(args, "library", False):
        libraries = client.get_libraries()
        if use_all:
            _print_libraries(client, libraries, count=count)
            return
        if item_id:
            lib = find_library(libraries, library_id=item_id)
            if not lib:
                print(f"Library id '{item_id}' not found. Available:")
                for lib in libraries:
                    print(f"  - [{lib.get('Id', '?')}] {lib.get('Name', '?')}")
                sys.exit(1)
            _print_libraries(client, [lib], count=count)
            return

        needle = query.lower()
        matches = [
            lib for lib in libraries
            if needle in (lib.get("Name") or "").lower()
        ]
        _print_libraries(client, matches, count=count)
        return

    # --media-item
    if use_all:
        probe = client.get_items(item_type=SEARCH_ITEM_TYPES, limit=0)
        total = int(probe.get("TotalRecordCount") or 0)
        if total > count:
            print(
                f"There are {total} media items on this server. "
                "Please narrow the results with --search, for example:\n"
                '  emby-cli search --media-item --search "title"'
            )
            sys.exit(1)
        if total == 0:
            print("No results.")
            return
        items = client.get_all_items(item_type=SEARCH_ITEM_TYPES)
        print_item_choices(items)
        print(f"\nTotal: {len(items)}")
        print()
        return

    if item_id:
        try:
            item = client.get_item_info(item_id)
        except Exception as exc:
            print(f"error: fetching item {item_id}: {exc}", file=sys.stderr)
            sys.exit(1)
        print_item_choices([item])
        print("\nTotal: 1")
        print()
        return

    items = client.search_items(
        query,
        item_types=SEARCH_ITEM_TYPES,
        limit=count,
    )
    if not items:
        print("No results.")
        return
    print_item_choices(items)
    print(f"\nTotal: {len(items)}")
    print()
