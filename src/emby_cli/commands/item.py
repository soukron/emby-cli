"""Browse playable media items (movies, episodes, audio, …)."""

from __future__ import annotations

import argparse

from emby_cli.client import EmbyClient
from emby_cli.commands.show import _print_media_item
from emby_cli.constants import SEARCH_COUNT_DEFAULT
from emby_cli.item_ops import (
    ITEM_TYPE_ALIASES,
    DownloadOpts,
    ItemResolutionError,
    build_item_listing_query,
    download_item_ids,
    download_items,
    fetch_item_listing,
    find_player,
    item_selector_id,
    normalize_item_type,
    play_item_ids,
    play_one_item,
    resolve_item,
)
from emby_cli.output import print_done, print_error
from emby_cli.resolve import pick_best_item, print_item_choices


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
    elif command == "play":
        query = _text(args, "query")
        item_id = item_selector_id(args)
        pick_best = getattr(args, "pick_best_item", False) is True
        if bool(query) == bool(item_id):
            return "provide exactly one media item QUERY or --id"
        if item_id and pick_best:
            return "--pick-best-item can only be used with QUERY"
    elif command == "download":
        query = _text(args, "query")
        item_id = item_selector_id(args)
        pick_best = getattr(args, "pick_best_item", False) is True
        if bool(query) == bool(item_id):
            return "provide exactly one media item QUERY or --id"
        if item_id and pick_best:
            return "--pick-best-item can only be used with QUERY"
    else:
        return "provide an item subcommand"

    raw_type = _text(args, "item_type")
    if raw_type and normalize_item_type(raw_type) is None:
        allowed = ", ".join(sorted(ITEM_TYPE_ALIASES.keys()))
        return f"error: --type must be one of {allowed}"

    year = _opt_int(args, "year")
    if year is not None and year < 0:
        return "error: --year must be >= 0"

    return None


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
    pick_best: bool = False,
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
        if pick_best and exc.matches:
            best = pick_best_item(exc.matches)
            if best is not None:
                print_item_choices(exc.matches, selected=best)
                return best
        _print_resolution_error(exc)
        raise SystemExit(1) from None


def _cmd_play(client: EmbyClient, args: argparse.Namespace) -> None:
    wait = getattr(args, "wait", False) is True
    pick_best = getattr(args, "pick_best_item", False) is True
    try:
        player_cmd = find_player(getattr(args, "player", None))
    except RuntimeError as exc:
        print_error(str(exc))
        raise SystemExit(1) from None

    item_id = item_selector_id(args)
    if item_id:
        rc = play_item_ids(
            client,
            item_id,
            player_cmd,
            raw_type=_text(args, "item_type"),
            wait=wait,
        )
        if rc != 0:
            raise SystemExit(rc)
        return

    item = _resolve_from_args(client, args, use_cache=True, pick_best=pick_best)
    rc = play_one_item(client, item, player_cmd, wait=wait)
    if rc != 0:
        raise SystemExit(rc)


def _cmd_download(client: EmbyClient, args: argparse.Namespace) -> None:
    opts = DownloadOpts.from_args(args)
    pick_best = getattr(args, "pick_best_item", False) is True
    if opts.dry_run:
        print("*** DRY RUN — no files will be downloaded ***\n")

    item_id = item_selector_id(args)
    if item_id:
        stats = download_item_ids(
            client,
            item_id,
            opts.output,
            method=opts.method,
            force=args.force,
            throttle=opts.throttle,
            dry_run=opts.dry_run,
            raw_type=_text(args, "item_type"),
            mirror_path=opts.mirror_path,
            path_strip=opts.path_strip,
        )
        print_done(stats)
        raise SystemExit(stats.exit_code())

    item = _resolve_from_args(client, args, use_cache=False, pick_best=pick_best)
    stats = download_items(
        client,
        [item],
        opts.output,
        method=opts.method,
        force=args.force,
        throttle=opts.throttle,
        dry_run=opts.dry_run,
        mirror_path=opts.mirror_path,
        path_strip=opts.path_strip,
    )
    print_done(stats)
    raise SystemExit(stats.exit_code())


def _cmd_item_listing(
    client: EmbyClient,
    args: argparse.Namespace,
    *,
    query: str,
    count: int | None,
) -> None:
    listing = build_item_listing_query(
        query=query,
        raw_type=_text(args, "item_type"),
        year=_opt_int(args, "year"),
        count=count,
        order_by=_text(args, "order_by"),
        desc=getattr(args, "desc", False) is True,
    )
    shown, available = fetch_item_listing(
        client,
        listing,
        use_cache=True,
    )
    if not shown:
        print("No results.")
        return
    print_item_choices(shown, sort_rows=False)
    _print_total(len(shown), available if available > len(shown) else None)


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
    client.no_data_cache = getattr(args, "no_cache", False) is True
    handlers = {
        "search": _cmd_search,
        "list": _cmd_list,
        "show": _cmd_show,
        "play": _cmd_play,
        "download": _cmd_download,
    }
    handlers[args.item_command](client, args)
