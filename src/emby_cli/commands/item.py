"""Browse playable media items (movies, episodes, audio, …)."""

from __future__ import annotations

import argparse

from emby_cli.client import EmbyClient
from emby_cli.commands.show import _print_media_item
from emby_cli.constants import SEARCH_COUNT_DEFAULT
from emby_cli.item_ops import (
    ITEM_TYPE_ALIASES,
    ItemResolutionError,
    filter_items,
    item_selector_id,
    item_types_for_api,
    normalize_item_type,
    resolve_item,
)
from emby_cli.output import print_error
from emby_cli.resolve import item_video_width, print_item_choices, sort_for_display
from emby_cli.util import item_remote_size


def _text(args: argparse.Namespace, name: str) -> str | None:
    value = getattr(args, name, None)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _opt_int(args: argparse.Namespace, name: str) -> int | None:
    value = getattr(args, name, None)
    return value if isinstance(value, int) else None


def _parse_count(value: object) -> int | None:
    text = str(value).strip().casefold()
    if text == "all":
        return None
    count = int(text)
    if count < 1:
        raise ValueError("--count must be >= 1")
    return count


def validate_item_args(args: argparse.Namespace) -> str | None:
    """Validate item arguments without opening a server connection."""
    command = getattr(args, "item_command", None)
    if command == "search":
        try:
            _parse_count(getattr(args, "count", SEARCH_COUNT_DEFAULT))
        except (TypeError, ValueError) as exc:
            return str(exc) if str(exc).startswith("--count") else "--count must be N or all"
    elif command == "list":
        pass
    elif command == "show":
        query = _text(args, "query")
        item_id = item_selector_id(args)
        if bool(query) == bool(item_id):
            return "provide exactly one media item QUERY or --id"
    else:
        return "provide an item subcommand"

    raw_type = _text(args, "item_type")
    if raw_type and normalize_item_type(raw_type) is None:
        allowed = ", ".join(sorted(ITEM_TYPE_ALIASES.keys()))
        return f"error: --type must be one of {allowed}"

    year = _opt_int(args, "year")
    if year is not None and year < 0:
        return "error: --year must be >= 0"

    order_by = _text(args, "order_by")
    if order_by == "items":
        return "--order-by items can only be used with library search"
    return None


def _sort_key_id(row: dict) -> tuple[int, int, str]:
    item_id = str(row.get("Id") or "")
    if item_id.isdigit():
        return (0, int(item_id), item_id)
    return (1, 0, item_id.casefold())


def _sort_item_rows(rows: list[dict], order_by: str | None, desc: bool) -> list[dict]:
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
    if order_by == "year":
        year_rows = [row for row in rows if row.get("ProductionYear") is not None]
        no_year_rows = [row for row in rows if row.get("ProductionYear") is None]
        year_rows = sorted(
            year_rows,
            key=lambda row: (
                int(row.get("ProductionYear") or 0),
                str(row.get("Name") or "").casefold(),
                _sort_key_id(row),
            ),
            reverse=desc,
        )
        return year_rows + no_year_rows
    if order_by == "size":
        with_size = [row for row in rows if item_remote_size(row) is not None]
        without_size = [row for row in rows if item_remote_size(row) is None]
        with_size = sorted(
            with_size,
            key=lambda row: (
                int(item_remote_size(row) or 0),
                str(row.get("Name") or "").casefold(),
                _sort_key_id(row),
            ),
            reverse=desc,
        )
        return with_size + without_size
    with_res = [row for row in rows if item_video_width(row) is not None]
    without_res = [row for row in rows if item_video_width(row) is None]
    with_res = sorted(
        with_res,
        key=lambda row: (
            int(item_video_width(row) or 0),
            str(row.get("Name") or "").casefold(),
            _sort_key_id(row),
        ),
        reverse=desc,
    )
    return with_res + without_res


def _print_total(shown: int, available: int | None = None) -> None:
    if available is not None and available > shown:
        print(f"\nTotal: {shown} (out of {available})\n")
    else:
        print(f"\nTotal: {shown}\n")


def _print_resolution_error(exc: ItemResolutionError) -> None:
    print_error(str(exc))
    if exc.matches:
        print_item_choices(exc.matches, sort_rows=True)


def _resolve_from_args(
    client: EmbyClient,
    args: argparse.Namespace,
    *,
    use_cache: bool,
    query: str | None = None,
) -> dict:
    try:
        return resolve_item(
            client,
            query=query if query is not None else _text(args, "query"),
            item_id=item_selector_id(args),
            raw_type=_text(args, "item_type"),
            use_cache=use_cache,
        )
    except ItemResolutionError as exc:
        _print_resolution_error(exc)
        raise SystemExit(1) from None


def _listing_rows(
    client: EmbyClient,
    args: argparse.Namespace,
    *,
    query: str,
    count: int | None,
) -> tuple[list[dict], list[dict]]:
    item_types = item_types_for_api(_text(args, "item_type"))
    items, _total = client.items.search(query, item_types=item_types, use_cache=True)
    items = filter_items(
        items,
        raw_type=_text(args, "item_type"),
        year=_opt_int(args, "year"),
    )
    items = _sort_item_rows(
        items,
        _text(args, "order_by"),
        bool(getattr(args, "desc", False)),
    )
    shown = items if count is None else items[:count]
    return items, shown


def _cmd_item_listing(
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
    print_item_choices(shown, sort_rows=False)
    _print_total(len(shown), len(all_rows))


def _cmd_search(client: EmbyClient, args: argparse.Namespace) -> None:
    query = _text(args, "query") or ""
    count = _parse_count(getattr(args, "count", SEARCH_COUNT_DEFAULT))
    _cmd_item_listing(client, args, query=query, count=count)


def _cmd_list(client: EmbyClient, args: argparse.Namespace) -> None:
    _cmd_item_listing(client, args, query="", count=None)


def _cmd_show(client: EmbyClient, args: argparse.Namespace) -> None:
    item = _resolve_from_args(client, args, use_cache=True)
    _print_media_item(item)


def cmd_item(client: EmbyClient, args: argparse.Namespace) -> None:
    """Validate and dispatch a nested item command."""
    error = validate_item_args(args)
    if error:
        print_error(error)
        raise SystemExit(1)
    client.no_data_cache = bool(getattr(args, "no_cache", False))
    handlers = {
        "search": _cmd_search,
        "list": _cmd_list,
        "show": _cmd_show,
    }
    handlers[args.item_command](client, args)
