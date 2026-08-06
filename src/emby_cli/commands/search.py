"""search command."""

from __future__ import annotations

import argparse

from emby_cli.client import EmbyClient
from emby_cli.util import format_size, item_remote_size

def cmd_search(client: EmbyClient, args: argparse.Namespace) -> None:
    uid = client.resolve_user_id()
    params = {
        "SearchTerm": args.query,
        "Limit": 25,
        "Recursive": "true",
        "Fields": "Path,MediaSources,Size",
        "IncludeItemTypes": "Movie,Episode,Audio,Video",
    }
    resp = client._get(f"/Users/{uid}/Items", params=params)
    items = resp.json().get("Items", [])

    if not items:
        print("No results.")
        return

    print(f"\n{'ID':<34} {'Name':<50} {'Type':<10} {'Size':>12}")
    print("-" * 108)
    for it in items:
        size = format_size(item_remote_size(it))
        print(f"{it['Id']:<34} {it['Name']:<50} {it['Type']:<10} {size:>12}")
    print()
