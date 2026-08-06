"""info command — session + server inventory."""

from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse

import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import INFO_RETRIES, INFO_TIMEOUT
from emby_cli.credentials import (
    CredentialError,
    resolve_operational_auth,
    resolve_server,
)

# Always shown (even when 0).
_PRIMARY_COUNTS = (
    ("movies", "MovieCount"),
    ("series", "SeriesCount"),
    ("episodes", "EpisodeCount"),
    ("songs", "SongCount"),
    ("albums", "AlbumCount"),
)

# Shown only when > 0.
_EXTRA_COUNTS = (
    ("boxsets", "BoxSetCount"),
    ("books", "BookCount"),
    ("trailers", "TrailerCount"),
    ("musicvideos", "MusicVideoCount"),
    ("artists", "ArtistCount"),
)


def _norm_host(url: str) -> str:
    p = urlparse(url if "://" in url else f"http://{url}")
    host = (p.hostname or "").lower()
    port = p.port
    if port and port not in (80, 443, 8096):
        return f"{host}:{port}"
    return host


def _addr_differs(configured: str, candidate: str | None) -> bool:
    if not candidate:
        return False
    return _norm_host(configured) != _norm_host(candidate)


def cmd_info(args: argparse.Namespace) -> None:
    try:
        server = resolve_server(args, prompt=False)
    except CredentialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    api_key, username, password = resolve_operational_auth(args)
    configured_user = username
    client = EmbyClient(server, api_key=api_key)
    probe_kw = {"timeout": INFO_TIMEOUT, "retries": INFO_RETRIES}

    try:
        user, info = client.probe_session(username=username, password=password)
    except (requests.RequestException, RuntimeError, ValueError, KeyError, TypeError) as exc:
        user_name = configured_user or "unknown"
        print("Connection")
        print(f"user: {user_name}")
        print(f"url: {client.server_url}")
        print()
        print("Server")
        print("server: not validated (name and version unavailable)")
        print(f"detail: {exc}", file=sys.stderr)
        return

    user_name = user.get("Name") or configured_user or user.get("Id") or "unknown"
    user_id = user.get("Id")
    if user_id:
        client.user_id = user_id

    print("Connection")
    print(f"user: {user_name}")
    print(f"url: {client.server_url}")
    print()

    print("Server")
    print(f"server: {info.get('ServerName') or info.get('Id') or 'unknown'}")
    print(f"version: {info.get('Version') or 'unknown'}")

    os_name = info.get("OperatingSystemDisplayName") or info.get("OperatingSystem")
    if os_name:
        print(f"os: {os_name}")
    server_id = info.get("Id")
    if server_id:
        print(f"id: {server_id}")
    if info.get("HasUpdateAvailable"):
        print("update: available")
    if _addr_differs(client.server_url, info.get("LocalAddress")):
        print(f"local: {info['LocalAddress']}")
    if _addr_differs(client.server_url, info.get("WanAddress")):
        print(f"wan: {info['WanAddress']}")
    print()

    print("Content")
    try:
        libraries = client.get_libraries(**probe_kw)
    except (requests.RequestException, RuntimeError, ValueError, KeyError, TypeError):
        print("libraries: unavailable")
        libraries = None

    if libraries is not None:
        print(f"libraries: {len(libraries)}")

    try:
        counts = client.get_item_counts(user_id=user_id, **probe_kw)
    except (requests.RequestException, RuntimeError, ValueError, KeyError, TypeError):
        print("counts: unavailable")
        return

    for label, key in _PRIMARY_COUNTS:
        val = counts.get(key)
        print(f"{label}: {val if val is not None else 'unavailable'}")

    for label, key in _EXTRA_COUNTS:
        val = counts.get(key)
        if isinstance(val, int) and val > 0:
            print(f"{label}: {val}")
