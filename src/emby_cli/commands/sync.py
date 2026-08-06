"""sync command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from emby_cli.client import EmbyClient
from emby_cli.download_ops import do_download, should_skip_item
from emby_cli.util import build_dest_path

def cmd_sync(client: EmbyClient, args: argparse.Namespace) -> None:
    """Download all media from all libraries (or a specific one)."""
    output = Path(args.output)
    downloadable = ("Movie", "Episode", "Audio", "Video")
    throttle = getattr(args, "throttle", False)
    method = getattr(args, "method", "download")
    libraries = client.get_libraries()

    if args.library:
        libraries = [l for l in libraries if l["Name"].lower() == args.library.lower()]
        if not libraries:
            print(f"Library '{args.library}' not found")
            sys.exit(1)

    total_dl, total_skip, total_err = 0, 0, 0

    for lib in libraries:
        print(f"\n{'='*60}")
        print(f"Library: {lib['Name']}")
        print(f"{'='*60}")

        items = client.get_all_items(parent_id=lib["Id"])
        targets = [i for i in items if i.get("Type") in downloadable]
        print(f"Found {len(targets)} items")

        for idx, item in enumerate(targets, 1):
            dest = build_dest_path(item, output)
            if should_skip_item(item, dest, method, args.force):
                total_skip += 1
                continue

            prefix = f"[{idx}/{len(targets)}]"
            print(f"\n{prefix} {item['Name']}")
            try:
                do_download(client, item["Id"], item, dest, method, throttle)
                total_dl += 1
            except Exception as exc:
                print(f"  ERROR: {exc}")
                total_err += 1

    print(f"\n{'='*60}")
    print(f"Sync complete. Downloaded: {total_dl}, Skipped: {total_skip}, Errors: {total_err}")
