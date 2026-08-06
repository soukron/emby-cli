"""login command — authenticate and cache AccessToken."""

from __future__ import annotations

import argparse
import sys

import requests

from emby_cli.client import EmbyClient
from emby_cli.credentials import CredentialError, resolve_login_credentials


def cmd_login(args: argparse.Namespace) -> None:
    try:
        server, username, password = resolve_login_credentials(args)
    except CredentialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    client = EmbyClient(server, api_key=None)
    try:
        user = client.ensure_user_session(username, password, force=True)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        sys.exit(1)

    name = (user or {}).get("Name") or username
    print(f"Logged in as {name} @ {client.server_url}")
