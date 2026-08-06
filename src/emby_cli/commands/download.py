"""download command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from emby_cli.client import EmbyClient
from emby_cli.download_ops import do_download, should_skip_item
from emby_cli.util import build_dest_path

def cmd_download(client: EmbyClient, args: argparse.Namespace) -> None:
    output = Path(args.output)
    downloadable = ("Movie", "Episode", "Audio", "Video")
    throttle = getattr(args, "throttle", False)
    method = getattr(args, "method", "download")

    if args.item_id:
        item_ids = [x.strip() for x in args.item_id.split(",") if x.strip()]
        total = len(item_ids)
        errors = 0
        for idx, iid in enumerate(item_ids, 1):
            prefix = f"[{idx}/{total}]" if total > 1 else ""
            try:
                item = client.get_item_info(iid)
            except Exception as exc:
                print(f"{prefix} ERROR fetching item {iid}: {exc}")
                errors += 1
                continue
            dest = build_dest_path(item, output)
            if should_skip_item(item, dest, method, args.force):
                print(f"{prefix} Skipping (already downloaded): {dest}")
                continue
            print(f"{prefix} Downloading ({method}): {item['Name']} -> {dest}")
            try:
                do_download(client, iid, item, dest, method, throttle)
            except Exception as exc:
                print(f"  ERROR: {exc}")
                errors += 1
        if total > 1:
            print(f"\nDone. Items: {total}, Errors: {errors}")
        return

    if not args.library:
        print("Specify --library or --item-id")
        sys.exit(1)

    libraries = client.get_libraries()
    lib = next((l for l in libraries if l["Name"].lower() == args.library.lower()), None)
    if not lib:
        print(f"Library '{args.library}' not found")
        sys.exit(1)

    items = client.get_all_items(parent_id=lib["Id"])
    targets = [i for i in items if i.get("Type") in downloadable]

    print(f"\nFound {len(targets)} items in '{lib['Name']}'")
    skipped = 0
    errors = 0

    for idx, item in enumerate(targets, 1):
        dest = build_dest_path(item, output)
        if should_skip_item(item, dest, method, args.force):
            skipped += 1
            continue

        prefix = f"[{idx}/{len(targets)}]"
        print(f"\n{prefix} {item['Name']}")
        try:
            do_download(client, item["Id"], item, dest, method, throttle)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            errors += 1

    print(f"\nDone. Downloaded: {len(targets) - skipped - errors}, "
          f"Skipped: {skipped}, Errors: {errors}")
