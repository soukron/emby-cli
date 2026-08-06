"""sync command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from emby_cli.client import EmbyClient
from emby_cli.download_ops import download_library_items
from emby_cli.output import Stats, print_done


def cmd_sync(client: EmbyClient, args: argparse.Namespace) -> None:
    """Download all media from all libraries (or a specific one)."""
    output = Path(args.output)
    throttle = float(getattr(args, "throttle", 0) or 0)
    method = getattr(args, "method", "download")
    libraries = client.get_libraries()

    if args.library:
        libraries = [l for l in libraries if l["Name"].lower() == args.library.lower()]
        if not libraries:
            all_libs = client.get_libraries()
            print(f"Library '{args.library}' not found. Available:")
            for l in all_libs:
                print(f"  - {l['Name']}")
            sys.exit(1)

    totals = Stats()
    for lib in libraries:
        stats = download_library_items(
            client,
            lib,
            output,
            method=method,
            force=args.force,
            throttle=throttle,
            show_section=True,
        )
        totals.ok += stats.ok
        totals.skip += stats.skip
        totals.error += stats.error

    print_done(totals, label="Sync complete")
    sys.exit(totals.exit_code())
