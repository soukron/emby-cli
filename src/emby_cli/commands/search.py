"""search command."""

from __future__ import annotations

import argparse
import sys

from emby_cli.client import EmbyClient
from emby_cli.resolve import print_item_choices


def cmd_search(client: EmbyClient, args: argparse.Namespace) -> None:
    count = getattr(args, "count", None)
    if count is not None and count < 1:
        print("error: --count must be >= 1", file=sys.stderr)
        sys.exit(1)

    items = client.search_items(
        args.query,
        item_types="Movie,Episode,Audio,Video",
        limit=count,  # None → all pages
    )
    if not items:
        print("No results.")
        return
    print_item_choices(items)
    print(f"\nTotal: {len(items)}")
    if count is not None:
        print(f"(limited by --count {count})")
    print()
