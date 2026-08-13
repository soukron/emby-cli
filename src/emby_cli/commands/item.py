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
    download_from_file,
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
from emby_cli.resolve import pick_best_item, print_item_choices, resolve_title_items


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
        from_file = getattr(args, "from_file", None)
        query = _text(args, "query")
        item_id = item_selector_id(args)
        pick_best = getattr(args, "pick_best_item", False) is True
        if from_file:
            if query or item_id:
                return "With --from-file, do not pass QUERY or --id"
        elif bool(query) == bool(item_id):
            return "provide exactly one media item QUERY or --id"
        elif item_id and pick_best:
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
        print_item_choices(exc.matches, sort_rows=True, leading_blank=True)


def _resolve_from_args(
    client: EmbyClient,
    args: argparse.Namespace,
    *,
    use_cache: bool,
    query: str | None = None,
    pick_best: bool = False,
    parse_query: bool | None = None,
) -> dict:
    if parse_query is None:
        parse_query = getattr(args, "parse_query", False) is True
    try:
        return resolve_item(
            client,
            query=query if query is not None else _text(args, "query"),
            item_id=item_selector_id(args),
            raw_type=_text(args, "item_type"),
            use_cache=use_cache,
            parse_query=parse_query,
        )
    except ItemResolutionError as exc:
        if pick_best and exc.matches:
            best = pick_best_item(exc.matches)
            if best is not None:
                print_item_choices(exc.matches, selected=best, leading_blank=True)
                return best
        _print_resolution_error(exc)
        raise SystemExit(1) from None


def _resolve_title_from_args(
    client: EmbyClient,
    args: argparse.Namespace,
    *,
    pick_best: bool = False,
    allow_season_all: bool = False,
) -> list[dict]:
    query = _text(args, "query")
    if not query:
        raise SystemExit(1)
    items = resolve_title_items(
        client,
        query,
        pick_best=pick_best,
        allow_season_all=allow_season_all,
    )
    if items is None:
        raise SystemExit(1)
    return items


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

    if getattr(args, "no_parse_query", False):
        item = _resolve_from_args(
            client,
            args,
            use_cache=not getattr(args, "no_cache", False),
            pick_best=pick_best,
            parse_query=False,
        )
        rc = play_one_item(client, item, player_cmd, wait=wait)
        if rc != 0:
            raise SystemExit(rc)
        return

    items = _resolve_title_from_args(client, args, pick_best=pick_best)
    rc = play_one_item(client, items[0], player_cmd, wait=wait)
    if rc != 0:
        raise SystemExit(rc)


def _cmd_download_from_file(client: EmbyClient, args: argparse.Namespace) -> None:
    opts = DownloadOpts.from_args(args)
    pick_best = getattr(args, "pick_best_item", False) is True
    if opts.dry_run:
        print("*** DRY RUN — no files will be downloaded ***\n")
    rc = download_from_file(
        client,
        args.from_file,
        opts.output,
        method=opts.method,
        force=args.force,
        throttle=opts.throttle,
        dry_run=opts.dry_run,
        pick_best=pick_best,
        mirror_path=opts.mirror_path,
        path_strip=opts.path_strip,
    )
    raise SystemExit(rc)


def _cmd_download(client: EmbyClient, args: argparse.Namespace) -> None:
    if getattr(args, "from_file", None):
        _cmd_download_from_file(client, args)
        return

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

    if getattr(args, "no_parse_query", False):
        item = _resolve_from_args(
            client,
            args,
            use_cache=True,
            pick_best=pick_best,
            parse_query=False,
        )
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

    items = _resolve_title_from_args(
        client,
        args,
        pick_best=pick_best,
        allow_season_all=True,
    )
    stats = download_items(
        client,
        items,
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
        parse_query=getattr(args, "parse_query", False) is True,
    )
    shown, available = fetch_item_listing(
        client,
        listing,
        use_cache=True,
    )
    if not shown:
        print("No results.")
        return
    print_item_choices(shown, sort_rows=False, leading_blank=True)
    _print_total(len(shown), available if available > len(shown) else None)


def _cmd_search(client: EmbyClient, args: argparse.Namespace) -> None:
    query = _text(args, "query") or ""
    count = _parse_count(getattr(args, "count", SEARCH_COUNT_DEFAULT))
    _cmd_item_listing(client, args, query=query, count=count)


def _cmd_list(client: EmbyClient, args: argparse.Namespace) -> None:
    _cmd_item_listing(client, args, query="", count=None)


def _cmd_show(client: EmbyClient, args: argparse.Namespace) -> None:
    item = _resolve_from_args(
        client,
        args,
        use_cache=True,
        parse_query=getattr(args, "parse_query", False) is True,
    )
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
