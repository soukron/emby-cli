"""logout command — revoke AccessToken and clear local cache."""

from __future__ import annotations

import argparse
import sys

import requests

from emby_cli.auth_cache import (
    AuthCacheEntry,
    clear_auth_cache,
    list_auth_cache_entries,
    load_auth_cache,
)
from emby_cli.client import EmbyClient
from emby_cli.credentials import (
    CredentialError,
    resolve_operational_auth,
    resolve_server,
)


def _resolve_cache_entry(args: argparse.Namespace) -> AuthCacheEntry:
    """Pick which cached session to log out of."""
    api_key, username, _password = resolve_operational_auth(args)
    if api_key:
        raise CredentialError(
            "logout applies to cached user sessions, not API keys"
        )

    server_arg = (getattr(args, "server", None) or "").strip() or None
    if not server_arg:
        # Same rule as resolve_server: only auto-pick when a single file exists.
        entries = list_auth_cache_entries()
        if len(entries) == 1:
            return entries[0]
        if not entries:
            raise CredentialError(
                "No cached session; nothing to log out"
            )
        listed = "\n".join(
            f"  - {e.username} @ {e.server_url}"
            for e in sorted(entries, key=lambda e: (e.server_url, e.username))
        )
        raise CredentialError(
            "Multiple cached sessions; provide --server (and --username if needed):\n"
            f"{listed}"
        )

    try:
        server = resolve_server(args, prompt=False)
    except CredentialError:
        server = server_arg.rstrip("/")

    entry = load_auth_cache(server_url=server, username=username)
    if entry is None:
        if username:
            raise CredentialError(
                f"No cached session for {username} @ {server}"
            )
        raise CredentialError(f"No cached session for {server}")
    return entry


def cmd_logout(args: argparse.Namespace) -> None:
    try:
        entry = _resolve_cache_entry(args)
    except CredentialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    client = EmbyClient(entry.server_url, api_key=None, use_auth_cache=False)
    client.access_token = entry.access_token
    client.user_id = entry.user_id
    client._username = entry.username

    try:
        client.logout_session()
    except (requests.RequestException, RuntimeError) as exc:
        print(f"warning: could not revoke token on server: {exc}", file=sys.stderr)

    clear_auth_cache(server_url=entry.server_url, username=entry.username)
    print(f"Logged out {entry.username} @ {entry.server_url}")
