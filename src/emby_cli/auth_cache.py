"""Persist Emby AccessToken sessions in a single kubeconfig-style store."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AuthCacheEntry:
    server_url: str
    username: str
    access_token: str
    user_id: str
    saved_at: str
    name: str = ""

    def __post_init__(self) -> None:
        self.server_url = self.server_url.rstrip("/")
        if not self.name:
            self.name = context_name(self.server_url, self.username)

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
            name=context_name(server_url, username),
        )


@dataclass
class AuthStore:
    current_context: str = ""
    contexts: list[AuthCacheEntry] = field(default_factory=list)


def context_name(server_url: str, username: str) -> str:
    return f"{username}@{server_url.rstrip('/')}"


def cache_dir() -> Path:
    return Path(os.environ.get("EMBY_CACHE_DIR", Path.home() / ".cache" / "emby-cli"))


def auth_store_path() -> Path:
    return cache_dir() / "auth.json"


def _auth_cache_disabled() -> bool:
    return os.environ.get("EMBY_NO_AUTH_CACHE") == "1"


def _entry_from_dict(data: dict) -> AuthCacheEntry | None:
    try:
        entry = AuthCacheEntry(
            server_url=str(data["server_url"]),
            username=str(data["username"]),
            access_token=str(data["access_token"]),
            user_id=str(data["user_id"]),
            saved_at=str(data.get("saved_at") or ""),
            name=str(data.get("name") or ""),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if not entry.access_token or not entry.user_id or not entry.server_url:
        return None
    if not entry.saved_at:
        entry.saved_at = datetime.now(timezone.utc).isoformat()
    return entry


def _parse_legacy_cache_file(path: Path) -> AuthCacheEntry | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return _entry_from_dict(data)


def _migrate_legacy_cache_files() -> AuthStore | None:
    """Import ``*.cache`` files into a new store; delete them on success."""
    root = cache_dir()
    if not root.is_dir():
        return None
    legacy = sorted(root.glob("*.cache"))
    if not legacy:
        return None

    entries: list[AuthCacheEntry] = []
    for path in legacy:
        entry = _parse_legacy_cache_file(path)
        if entry is not None:
            entries.append(entry)
    if not entries:
        return None

    by_name: dict[str, AuthCacheEntry] = {}
    for entry in entries:
        prev = by_name.get(entry.name)
        if prev is None or entry.saved_at >= prev.saved_at:
            by_name[entry.name] = entry
    merged = list(by_name.values())
    merged.sort(key=lambda e: e.saved_at, reverse=True)
    store = AuthStore(current_context=merged[0].name, contexts=merged)
    save_store(store)
    for path in legacy:
        try:
            path.unlink()
        except OSError:
            pass
    return store


def load_store() -> AuthStore:
    """Load ``auth.json``, migrating legacy ``*.cache`` files if needed."""
    if _auth_cache_disabled():
        return AuthStore()

    path = auth_store_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return AuthStore()
        contexts: list[AuthCacheEntry] = []
        for item in data.get("contexts") or []:
            if isinstance(item, dict):
                entry = _entry_from_dict(item)
                if entry is not None:
                    contexts.append(entry)
        current = str(data.get("current_context") or "")
        if current and not any(c.name == current for c in contexts):
            current = contexts[0].name if contexts else ""
        elif not current and contexts:
            current = max(contexts, key=lambda e: e.saved_at).name
        return AuthStore(current_context=current, contexts=contexts)

    migrated = _migrate_legacy_cache_files()
    return migrated if migrated is not None else AuthStore()


def save_store(store: AuthStore) -> None:
    if _auth_cache_disabled():
        return
    path = auth_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "current_context": store.current_context,
        "contexts": [asdict(c) for c in store.contexts],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def list_contexts() -> list[AuthCacheEntry]:
    store = load_store()
    return sorted(store.contexts, key=lambda e: (e.server_url, e.username))


def get_active_entry() -> AuthCacheEntry | None:
    store = load_store()
    if not store.current_context:
        return None
    for entry in store.contexts:
        if entry.name == store.current_context:
            return entry
    return None


def upsert_context(entry: AuthCacheEntry, *, activate: bool = True) -> None:
    if _auth_cache_disabled():
        return
    store = load_store()
    entry = AuthCacheEntry(
        server_url=entry.server_url,
        username=entry.username,
        access_token=entry.access_token,
        user_id=entry.user_id,
        saved_at=entry.saved_at or datetime.now(timezone.utc).isoformat(),
        name=entry.name or context_name(entry.server_url, entry.username),
    )
    store.contexts = [c for c in store.contexts if c.name != entry.name]
    store.contexts.append(entry)
    if activate:
        store.current_context = entry.name
    save_store(store)


def remove_context(
    *,
    name: str | None = None,
    server_url: str | None = None,
    username: str | None = None,
) -> bool:
    """Remove a context. Returns True if something was removed."""
    if _auth_cache_disabled():
        return False
    store = load_store()
    if name is None and server_url is not None and username is not None:
        name = context_name(server_url, username)
    if not name:
        return False
    before = len(store.contexts)
    store.contexts = [c for c in store.contexts if c.name != name]
    if len(store.contexts) == before:
        return False
    if store.current_context == name:
        if store.contexts:
            store.current_context = max(
                store.contexts, key=lambda e: e.saved_at
            ).name
        else:
            store.current_context = ""
    save_store(store)
    return True


def set_current_context(name: str) -> AuthCacheEntry:
    """Set ``current_context`` by exact name or unique server URL match."""
    store = load_store()
    needle = name.strip()
    matches = [c for c in store.contexts if c.name == needle]
    if not matches:
        # Unique match by server_url or username@server fragment.
        by_server = [
            c for c in store.contexts
            if c.server_url == needle.rstrip("/") or c.name.endswith(f"@{needle.rstrip('/')}")
        ]
        if len(by_server) == 1:
            matches = by_server
        else:
            by_user_server = [
                c for c in store.contexts
                if c.name == needle or c.username == needle
            ]
            if len(by_user_server) == 1:
                matches = by_user_server
    if len(matches) != 1:
        raise KeyError(f"context '{name}' not found")
    entry = matches[0]
    store.current_context = entry.name
    save_store(store)
    return entry


def load_auth_cache(
    *,
    server_url: str,
    username: str | None = None,
    cache_file: Path | None = None,
) -> AuthCacheEntry | None:
    """Load a session for *server_url* (optional *username*).

    *cache_file* is ignored (legacy API); the unified store is always used.
    """
    del cache_file  # legacy kwarg
    if _auth_cache_disabled():
        return None
    store = load_store()
    server = server_url.rstrip("/")
    matches = [c for c in store.contexts if c.server_url == server]
    if username is not None:
        matches = [c for c in matches if c.username == username]
    if not matches:
        return None
    if username is not None:
        return matches[0]
    # Prefer active context if it matches this server.
    for c in matches:
        if c.name == store.current_context:
            return c
    return max(matches, key=lambda e: e.saved_at)


def save_auth_cache(
    entry: AuthCacheEntry,
    cache_file: Path | None = None,
) -> None:
    del cache_file
    upsert_context(entry, activate=True)


def clear_auth_cache(
    *,
    server_url: str | None = None,
    username: str | None = None,
    cache_file: Path | None = None,
) -> None:
    del cache_file
    if server_url is not None and username is not None:
        remove_context(server_url=server_url, username=username)


def list_auth_cache_entries() -> list[AuthCacheEntry]:
    return list_contexts()


# Back-compat aliases used by older tests / docs.
def auth_cache_file(server_url: str, username: str) -> Path:
    """Deprecated path helper; returns store path (not per-user files)."""
    del server_url, username
    return auth_store_path()


def unique_cached_server_urls() -> list[str]:
    return sorted({e.server_url for e in list_auth_cache_entries()})
