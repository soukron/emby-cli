"""list command."""

from __future__ import annotations

import argparse
import sys

from emby_cli.client import EmbyClient
from emby_cli.constants import DOWNLOADABLE_TYPES
from emby_cli.resolve import print_item_choices


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
        targets = [i for i in items if i.get("Type") in DOWNLOADABLE_TYPES]
        print_item_choices(targets)
        print(f"\nTotal downloadable items: {len(targets)}")
    else:
        print("\nLibraries on server:")
        for lib in libraries:
            count = client.get_items(parent_id=lib["Id"], limit=0)
            print(f"  [{lib['Id'][:8]}] {lib['Name']:<30} ({count.get('TotalRecordCount', '?')} items)")
        print()
