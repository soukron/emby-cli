"""list command."""

from __future__ import annotations

import argparse
import sys

from emby_cli.client import EmbyClient
from emby_cli.util import format_size, item_remote_size

def cmd_list(client: EmbyClient, args: argparse.Namespace) -> None:
    libraries = client.get_libraries()

    if args.library:
        lib = next((l for l in libraries if l["Name"].lower() == args.library.lower()), None)
        if not lib:
            print(f"Library '{args.library}' not found. Available:")
            for l in libraries:
                print(f"  - {l['Name']}")
            sys.exit(1)
        items = client.get_all_items(parent_id=lib["Id"])
        print(f"\n{'Name':<60} {'Type':<12} {'Size':>12}")
        print("-" * 86)
        for it in items:
            if it.get("Type") not in ("Movie", "Episode", "Audio", "Video"):
                continue
            size = format_size(item_remote_size(it))
            print(f"{it['Name']:<60} {it['Type']:<12} {size:>12}")
        print(f"\nTotal downloadable items: {len([i for i in items if i.get('Type') in ('Movie','Episode','Audio','Video')])}")
    else:
        print("\nLibraries on server:")
        for lib in libraries:
            count = client.get_items(parent_id=lib["Id"], limit=0)
            print(f"  [{lib['Id'][:8]}] {lib['Name']:<30} ({count.get('TotalRecordCount', '?')} items)")
        print()
