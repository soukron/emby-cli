"""version command."""

from __future__ import annotations

import argparse
import sys

import requests

from emby_cli.client import EmbyClient
from emby_cli.version import get_version


def cmd_version(args: argparse.Namespace) -> None:
    print(f"emby-cli: {get_version()}")

    has_server = bool(getattr(args, "server", None))
    has_creds = bool(getattr(args, "api_key", None) or getattr(args, "username", None))
    if not has_server or not has_creds:
        return

    client = EmbyClient(args.server, api_key=args.api_key)
    try:
        _user, info = client.probe_session(
            username=args.username if args.username is not None else None,
            password=args.password if args.password is not None else "",
        )
    except (requests.RequestException, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print("server: not validated (name and version unavailable)")
        print(f"detail: {exc}", file=sys.stderr)
        return

    name = info.get("ServerName") or info.get("Id") or "Emby"
    ver = info.get("Version") or "unknown"
    print(f"server: {ver} ({name})")
