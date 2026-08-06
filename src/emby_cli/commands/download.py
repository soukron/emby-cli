"""download command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from emby_cli.client import EmbyClient
from emby_cli.download_ops import download_library_items, download_one_item
from emby_cli.output import Stats, print_done, print_error


def cmd_download(client: EmbyClient, args: argparse.Namespace) -> None:
    output = Path(args.output)
    throttle = float(getattr(args, "throttle", 0) or 0)
    method = getattr(args, "method", "download")
    stats = Stats()

    if args.item_id:
        item_ids = [x.strip() for x in args.item_id.split(",") if x.strip()]
        total = len(item_ids)
        for idx, iid in enumerate(item_ids, 1):
            try:
                item = client.get_item_info(iid)
            except Exception as exc:
                print_error(f"fetching item {iid}: {exc}", idx=idx, total=total)
                stats.error += 1
                continue
            result = download_one_item(
                client,
                item,
                output,
                method=method,
                force=args.force,
                throttle=throttle,
                idx=idx if total > 1 else None,
                total=total if total > 1 else None,
            )
            if result == "ok":
                stats.ok += 1
            elif result == "skip":
                stats.skip += 1
            elif result == "error":
                stats.error += 1
        print_done(stats)
        sys.exit(stats.exit_code())

    if not args.library:
        print("Specify --library or --item-id")
        sys.exit(1)

    libraries = client.get_libraries()
    lib = next((l for l in libraries if l["Name"].lower() == args.library.lower()), None)
    if not lib:
        print(f"Library '{args.library}' not found. Available:")
        for l in libraries:
            print(f"  - {l['Name']}")
        sys.exit(1)

    stats = download_library_items(
        client,
        lib,
        output,
        method=method,
        force=args.force,
        throttle=throttle,
        show_section=False,
    )
    print_done(stats)
    sys.exit(stats.exit_code())
