"""download command — legacy wrapper over item and library download helpers."""

from __future__ import annotations

import argparse
import sys

from emby_cli.client import EmbyClient
from emby_cli.deprecation import warn_deprecated
from emby_cli.download_ops import find_library, library_rows, match_libraries
from emby_cli.item_ops import (
    DownloadOpts,
    download_from_file,
    download_item_ids,
    download_items,
)
from emby_cli.library_ops import download_library
from emby_cli.mode_args import (
    mode_is_item,
    mode_is_library,
    resolve_item_id,
    resolve_query,
)
from emby_cli.output import print_done
from emby_cli.resolve import (
    print_available_libraries,
    print_library_choices,
    resolve_title_items,
)


def validate_download_args(args: argparse.Namespace) -> str | None:
    """Return an error message if mode/selectors are invalid; else ``None``."""
    if mode_is_item(args):
        query, err = resolve_query(args)
        if err:
            return err
        item_id = resolve_item_id(args, include_env=not query)
        if bool(item_id) == bool(query):
            return "With --item, provide exactly one of --id or QUERY/--search"
        return None

    if mode_is_library(args):
        if bool(getattr(args, "pick_best_item", False)):
            return "--pick-best-item cannot be used with --library"
        query, err = resolve_query(args)
        if err:
            return err
        library_id = (getattr(args, "id", None) or "").strip() or None
        if bool(library_id) == bool(query):
            return "With --library, provide exactly one of --id or QUERY/--search"
        return None

    if getattr(args, "from_file", None):
        if (getattr(args, "id", None) or "").strip() or (
            getattr(args, "search", None) or ""
        ).strip():
            return "With --from-file, do not pass --id or --search"
        return None

    return "Specify --item, --library, or --from-file"


def _cmd_download_item(client: EmbyClient, args: argparse.Namespace) -> None:
    opts = DownloadOpts.from_args(args)
    pick_best = bool(getattr(args, "pick_best_item", False))
    search, _ = resolve_query(args)
    item_id = resolve_item_id(args, include_env=not search)

    if opts.dry_run:
        print("*** DRY RUN — no files will be downloaded ***\n")

    if item_id:
        stats = download_item_ids(
            client,
            item_id,
            opts.output,
            method=opts.method,
            force=args.force,
            throttle=opts.throttle,
            dry_run=opts.dry_run,
            mirror_path=opts.mirror_path,
            path_strip=opts.path_strip,
        )
        print_done(stats)
        sys.exit(stats.exit_code())

    items = resolve_title_items(
        client,
        search,
        pick_best=pick_best,
        allow_season_all=True,
    )
    if items is None:
        sys.exit(1)

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
    sys.exit(stats.exit_code())


def _cmd_download_library(client: EmbyClient, args: argparse.Namespace) -> None:
    opts = DownloadOpts.from_args(args)
    library_id = (getattr(args, "id", None) or "").strip() or None
    search, _ = resolve_query(args)

    if opts.dry_run:
        print("*** DRY RUN — no files will be downloaded ***\n")

    libraries = client.get_libraries()
    if library_id:
        lib = find_library(libraries, library_id=library_id)
        if not lib:
            print(f"Library id '{library_id}' not found. Available:")
            print_available_libraries(libraries)
            sys.exit(1)
    else:
        matches = match_libraries(libraries, search or "")
        if not matches:
            print(f"Library '{search}' not found. Available:")
            print_available_libraries(libraries)
            sys.exit(1)
        if len(matches) > 1:
            print(
                f"Multiple matches ({len(matches)}). "
                "Re-run with --id, for example:\n"
                f'  emby-cli download --library --id {matches[0].get("Id", "<id>")}'
            )
            print_library_choices(library_rows(client, matches))
            sys.exit(1)
        lib = matches[0]

    stats = download_library(
        client,
        lib,
        opts.output,
        method=opts.method,
        force=args.force,
        throttle=opts.throttle,
        show_section=True,
        dry_run=opts.dry_run,
        mirror_path=opts.mirror_path,
        path_strip=opts.path_strip,
    )
    print_done(stats)
    sys.exit(stats.exit_code())


def _cmd_download_from_file(client: EmbyClient, args: argparse.Namespace) -> None:
    opts = DownloadOpts.from_args(args)
    pick_best = bool(getattr(args, "pick_best_item", False))
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
    sys.exit(rc)


def cmd_download(client: EmbyClient, args: argparse.Namespace) -> None:
    warn_deprecated("download")
    err = validate_download_args(args)
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)

    if mode_is_item(args):
        _cmd_download_item(client, args)
        return
    if mode_is_library(args):
        _cmd_download_library(client, args)
        return
    if getattr(args, "from_file", None):
        _cmd_download_from_file(client, args)
        return
    print("Specify --item, --library, or --from-file")
    sys.exit(1)
