"""Persist Emby AccessToken sessions on disk (never passwords)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AuthCacheEntry:
    server_url: str
    username: str
    access_token: str
    user_id: str
    saved_at: str

    @classmethod
    def create(
        cls,
        server_url: str,
        username: str,
        access_token: str,
        user_id: str,
    ) -> AuthCacheEntry:
        return cls(
            server_url=server_url.rstrip("/"),
            username=username,
            access_token=access_token,
            user_id=user_id,
            saved_at=datetime.now(timezone.utc).isoformat(),
        )


def cache_dir() -> Path:
    return Path(os.environ.get("EMBY_CACHE_DIR", Path.home() / ".cache" / "emby-cli"))


def cache_key(server_url: str, username: str) -> str:
    payload = f"{server_url.rstrip('/')}\0{username}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def auth_cache_file(server_url: str, username: str) -> Path:
    return cache_dir() / f"{cache_key(server_url, username)}.cache"


def _auth_cache_disabled() -> bool:
    return os.environ.get("EMBY_NO_AUTH_CACHE") == "1"


def load_auth_cache(
    *,
    server_url: str,
    username: str | None = None,
    cache_file: Path | None = None,
) -> AuthCacheEntry | None:
    if _auth_cache_disabled():
        return None

    if cache_file is not None:
        return _read_entry(cache_file, server_url=server_url, username=username)

    if username is not None:
        return _read_entry(
            auth_cache_file(server_url, username),
            server_url=server_url,
            username=username,
        )

    return _find_latest_for_server(server_url)


def save_auth_cache(
    entry: AuthCacheEntry,
    cache_file: Path | None = None,
) -> None:
    if _auth_cache_disabled():
        return

    path = cache_file or auth_cache_file(entry.server_url, entry.username)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(entry), indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def clear_auth_cache(
    *,
    server_url: str | None = None,
    username: str | None = None,
    cache_file: Path | None = None,
) -> None:
    if cache_file is not None:
        if cache_file.is_file():
            cache_file.unlink()
        return
    if server_url is not None and username is not None:
        path = auth_cache_file(server_url, username)
        if path.is_file():
            path.unlink()


def _parse_entry(path: Path) -> AuthCacheEntry | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entry = AuthCacheEntry(**data)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if not entry.access_token or not entry.user_id or not entry.server_url:
        return None
    entry.server_url = entry.server_url.rstrip("/")
    return entry


def list_auth_cache_entries() -> list[AuthCacheEntry]:
    """Return all valid cache entries (empty if cache disabled or missing)."""
    if _auth_cache_disabled():
        return []
    root = cache_dir()
    if not root.is_dir():
        return []
    entries: list[AuthCacheEntry] = []
    for path in root.glob("*.cache"):
        entry = _parse_entry(path)
        if entry is not None:
            entries.append(entry)
    return entries


def unique_cached_server_urls() -> list[str]:
    """Distinct ``server_url`` values from cache, sorted."""
    return sorted({e.server_url for e in list_auth_cache_entries()})


def _read_entry(
    path: Path,
    *,
    server_url: str,
    username: str | None,
) -> AuthCacheEntry | None:
    entry = _parse_entry(path)
    if entry is None:
        return None
    if entry.server_url != server_url.rstrip("/"):
        return None
    if username is not None and entry.username != username:
        return None
    return entry


def _find_latest_for_server(server_url: str) -> AuthCacheEntry | None:
    matches = [
        e for e in list_auth_cache_entries()
        if e.server_url == server_url.rstrip("/")
    ]
    if not matches:
        return None
    matches.sort(key=lambda e: e.saved_at, reverse=True)
    return matches[0]
