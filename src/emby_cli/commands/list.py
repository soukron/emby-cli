"""list command."""

from __future__ import annotations

import argparse
import sys

from emby_cli.client import EmbyClient
from emby_cli.constants import DOWNLOADABLE_TYPES
from emby_cli.resolve import print_item_choices, print_library_choices


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
        if not targets:
            print("No results.")
            return
        print_item_choices(targets)
        print(f"\nTotal: {len(targets)}")
        print()
        return

    if not libraries:
        print("No results.")
        return

    # Fetch all library counts first, then print one table.
    rows: list[dict] = []
    for lib in libraries:
        page = client.get_items(parent_id=lib["Id"], limit=0)
        rows.append({
            "Id": lib.get("Id", ""),
            "Name": lib.get("Name") or "?",
            "Type": lib.get("CollectionType") or lib.get("Type") or "Library",
            "ItemCount": page.get("TotalRecordCount", 0),
        })

    print_library_choices(rows)
    print(f"\nTotal: {len(rows)}")
    print()
