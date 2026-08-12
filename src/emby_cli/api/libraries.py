"""Emby library view operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from emby_cli.data_cache import delete_json

if TYPE_CHECKING:
    from emby_cli.client import EmbyClient


class LibrariesService:
    """Entity service for Emby library views (``/Users/{uid}/Views``)."""

    def __init__(self, client: EmbyClient):
        self.client = client

    def _catalog_key(self) -> str:
        uid = self.client.resolve_user_id()
        return f"v2:libraries:{self.client.server_url}:{uid}"

    def list(self, *, use_cache: bool = True) -> list[dict]:
        """Return every library view for the current user."""
        key = self._catalog_key()
        if use_cache:
            cached = self.client._cache_read(key)
            if isinstance(cached, list):
                return cached
        uid = self.client.resolve_user_id()
        libraries = self.client._get(f"/Users/{uid}/Views").json().get("Items", [])
        if use_cache:
            self.client._cache_write(key, libraries)
        return libraries

    def search(self, query: str, *, use_cache: bool = True) -> list[dict]:
        """Search library names locally over the complete catalog."""
        needle = query.strip().casefold()
        libraries = self.list(use_cache=use_cache)
        if not needle:
            return libraries
        return [
            lib
            for lib in libraries
            if needle in str(lib.get("Name") or "").casefold()
        ]

    def invalidate_catalog(self) -> None:
        delete_json(self._catalog_key())
