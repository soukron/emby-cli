"""Browse Emby library views."""

from __future__ import annotations

import argparse

from emby_cli.client import EmbyClient
from emby_cli.commands.show import _print_library
from emby_cli.constants import SEARCH_COUNT_DEFAULT, SHOW_LIBRARY_ITEM_TYPES
from emby_cli.download_ops import library_rows
from emby_cli.library_ops import (
    LIBRARY_TYPE_ALIASES,
    LibraryResolutionError,
    filter_libraries_by_type,
    library_selector_id,
    normalize_library_type,
    resolve_library,
)
from emby_cli.output import print_error
from emby_cli.resolve import print_library_choices, sort_for_display


def _text(args: argparse.Namespace, name: str) -> str | None:
    value = getattr(args, name, None)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _parse_count(value: object) -> int | None:
    text = str(value).strip().casefold()
    if text == "all":
        return None
    count = int(text)
    if count < 1:
        raise ValueError("--count must be >= 1")
    return count


def validate_library_args(args: argparse.Namespace) -> str | None:
    """Validate library arguments without opening a server connection."""
    command = getattr(args, "library_command", None)
    if command == "search":
        try:
            _parse_count(getattr(args, "count", SEARCH_COUNT_DEFAULT))
        except (TypeError, ValueError) as exc:
            return str(exc) if str(exc).startswith("--count") else "--count must be N or all"
    elif command == "list":
        pass
    elif command == "show":
        query = _text(args, "query")
        library_id = library_selector_id(args)
        if bool(query) == bool(library_id):
            return "provide exactly one library QUERY or --id"
    else:
        return "provide a library subcommand"

    raw_type = _text(args, "lib_type")
    if raw_type and normalize_library_type(raw_type) is None:
        allowed = ", ".join(sorted(LIBRARY_TYPE_ALIASES.keys()))
        return f"error: --type must be one of {allowed}"
    return None


def _sort_key_id(row: dict) -> tuple[int, int, str]:
    item_id = str(row.get("Id") or "")
    if item_id.isdigit():
        return (0, int(item_id), item_id)
    return (1, 0, item_id.casefold())


def _sort_library_rows(rows: list[dict], order_by: str | None, desc: bool) -> list[dict]:
    if not order_by:
        return sort_for_display(rows)
    if order_by == "name":
        return sorted(
            rows,
            key=lambda row: str(row.get("Name") or "").casefold(),
            reverse=desc,
        )
    if order_by == "id":
        return sorted(rows, key=_sort_key_id, reverse=desc)
    if order_by == "items":
        return sorted(
            rows,
            key=lambda row: (
                int(row["ItemCount"]) if row.get("ItemCount") is not None else -1
            ),
            reverse=desc,
        )
    return sort_for_display(rows)


def _print_libraries(rows: list[dict], *, sort_rows: bool = True) -> None:
    if sort_rows:
        rows = sort_for_display(rows)
    print_library_choices(rows, sort_rows=False)


def _print_resolution_error(exc: LibraryResolutionError) -> None:
    print_error(str(exc))
    if exc.matches:
        _print_libraries(library_rows_from_matches(exc.matches), sort_rows=True)


def library_rows_from_matches(libraries: list[dict]) -> list[dict]:
    return [
        {
            "Id": lib.get("Id") or "",
            "Name": lib.get("Name") or "?",
            "Type": lib.get("CollectionType") or lib.get("Type") or "Library",
            "ItemCount": lib.get("ItemCount"),
        }
        for lib in libraries
    ]


def _resolve_from_args(
    client: EmbyClient,
    args: argparse.Namespace,
    *,
    use_cache: bool,
    query: str | None = None,
) -> dict:
    try:
        return resolve_library(
            client,
            query=query if query is not None else _text(args, "query"),
            library_id=library_selector_id(args),
            use_cache=use_cache,
        )
    except LibraryResolutionError as exc:
        _print_resolution_error(exc)
        raise SystemExit(1) from None


def _listing_rows(
    client: EmbyClient,
    args: argparse.Namespace,
    *,
    query: str,
    count: int | None,
) -> tuple[list[dict], list[dict]]:
    libraries = client.libraries.search(query, use_cache=True)
    libraries = filter_libraries_by_type(libraries, _text(args, "lib_type"))
    rows = library_rows(
        client,
        libraries,
        item_types=SHOW_LIBRARY_ITEM_TYPES,
    )
    rows = _sort_library_rows(
        rows,
        _text(args, "order_by"),
        bool(getattr(args, "desc", False)),
    )
    shown = rows if count is None else rows[:count]
    return rows, shown


def _cmd_library_listing(
    client: EmbyClient,
    args: argparse.Namespace,
    *,
    query: str,
    count: int | None,
) -> None:
    all_rows, shown = _listing_rows(client, args, query=query, count=count)
    if not shown:
        print("No results.")
        return
    _print_libraries(shown, sort_rows=False)
    if len(shown) < len(all_rows):
        print(f"\nTotal: {len(shown)} (out of {len(all_rows)})\n")
    else:
        print(f"\nTotal: {len(shown)}\n")


def _cmd_search(client: EmbyClient, args: argparse.Namespace) -> None:
    query = _text(args, "query") or ""
    count = _parse_count(getattr(args, "count", SEARCH_COUNT_DEFAULT))
    _cmd_library_listing(client, args, query=query, count=count)


def _cmd_list(client: EmbyClient, args: argparse.Namespace) -> None:
    _cmd_library_listing(client, args, query="", count=None)


def _cmd_show(client: EmbyClient, args: argparse.Namespace) -> None:
    lib = _resolve_from_args(client, args, use_cache=True)
    _print_library(client, lib)


def cmd_library(client: EmbyClient, args: argparse.Namespace) -> None:
    """Validate and dispatch a nested library command."""
    error = validate_library_args(args)
    if error:
        print_error(error)
        raise SystemExit(1)
    client.no_data_cache = bool(getattr(args, "no_cache", False))
    handlers = {
        "search": _cmd_search,
        "list": _cmd_list,
        "show": _cmd_show,
    }
    handlers[args.library_command](client, args)
