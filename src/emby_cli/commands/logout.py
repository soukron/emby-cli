"""logout command — revoke AccessToken and clear local context."""

from __future__ import annotations

import argparse
import sys

import requests

from emby_cli.auth_cache import (
    AuthCacheEntry,
    clear_auth_cache,
    get_active_entry,
    load_auth_cache,
)
from emby_cli.client import EmbyClient
from emby_cli.credentials import (
    CredentialError,
    resolve_operational_auth,
)


def _resolve_cache_entry(args: argparse.Namespace) -> AuthCacheEntry:
    """Pick which cached session to log out of (default: active context)."""
    api_key, username, _password = resolve_operational_auth(args)
    if api_key:
        raise CredentialError(
            "logout applies to cached user sessions, not API keys"
        )

    server_arg = (getattr(args, "server", None) or "").strip() or None
    if not server_arg and username is None:
        active = get_active_entry()
        if active is None:
            raise CredentialError("No cached session; nothing to log out")
        return active

    server = (server_arg or "").rstrip("/")
    if not server:
        active = get_active_entry()
        if active is None:
            raise CredentialError("No cached session; nothing to log out")
        server = active.server_url

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
