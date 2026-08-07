"""version command."""

from __future__ import annotations

import argparse
import sys

import requests

from emby_cli.client import EmbyClient
from emby_cli.credentials import (
    CredentialError,
    resolve_operational_auth,
    resolve_server,
)
from emby_cli.version import get_version


def cmd_version(args: argparse.Namespace) -> None:
    print(f"emby-cli: {get_version()}")

    try:
        server = resolve_server(args, prompt=False)
    except CredentialError:
        return

    api_key, username, password = resolve_operational_auth(args)
    client = EmbyClient(server, api_key=api_key)
    try:
        _user, info = client.probe_session(username=username, password=password)
    except (requests.RequestException, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print("server: not validated (name and version unavailable)")
        print(f"detail: {exc}", file=sys.stderr)
        return

    name = info.get("ServerName") or info.get("Id") or "Emby"
    ver = info.get("Version") or "unknown"
    print(f"server: {ver} ({name})")
