"""Emby BoxSet collection operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from emby_cli.data_cache import delete_json

if TYPE_CHECKING:
    from emby_cli.client import EmbyClient


COLLECTION_FIELDS = "ChildCount,ProductionYear,DisplayOrder,SortName"
COLLECTION_DETAIL_FIELDS = COLLECTION_FIELDS + ",Overview"


class CollectionsService:
    """Entity service for Emby ``BoxSet`` resources."""

    def __init__(self, client: EmbyClient):
        self.client = client

    def _catalog_key(self) -> str:
        uid = self.client.resolve_user_id()
        return f"v2:collections:{self.client.server_url}:{uid}"

    def list(self, *, use_cache: bool = True) -> list[dict]:
        """Return the complete collection catalog."""
        key = self._catalog_key()
        if use_cache:
            cached = self.client._cache_read(key)
            if isinstance(cached, list):
                return cached
        collections = self.client.items.list_all(
            item_types="BoxSet",
            fields=COLLECTION_FIELDS,
            use_cache=False,
        )
        if use_cache:
            self.client._cache_write(key, collections)
        return collections

    def search(self, query: str, *, use_cache: bool = True) -> list[dict]:
        """Search collection names locally over the complete catalog."""
        needle = query.strip().casefold()
        collections = self.list(use_cache=use_cache)
        if not needle:
            return collections
        return [
            item
            for item in collections
            if needle in str(item.get("Name") or "").casefold()
        ]

    def create(
        self,
        name: str,
        *,
        item_ids: list[str] | None = None,
        parent_id: str | None = None,
        is_locked: bool = False,
    ) -> dict:
        params: dict = {
            "Name": name,
            "IsLocked": str(is_locked).lower(),
        }
        if item_ids:
            params["Ids"] = ",".join(item_ids)
        if parent_id:
            params["ParentId"] = parent_id
        result = self.client._post(
            "/Collections",
            params=params,
            retries=1,
        ).json()
        self.invalidate_catalog()
        return result

    def add_items(self, collection_id: str, item_ids: list[str]) -> None:
        self.client._post(
            f"/Collections/{collection_id}/Items",
            params={"Ids": ",".join(item_ids)},
        )
        self.invalidate(collection_id)

    def remove_items(self, collection_id: str, item_ids: list[str]) -> None:
        self.client._delete(
            f"/Collections/{collection_id}/Items",
            params={"Ids": ",".join(item_ids)},
        )
        self.invalidate(collection_id)

    def delete(self, collection_id: str) -> None:
        item = self.client.items.get(collection_id, use_cache=False)
        if item.get("Type") != "BoxSet":
            actual = item.get("Type") or "unknown"
            raise ValueError(
                f"refusing to delete item {collection_id}: expected BoxSet, got {actual}"
            )
        self.client.items.delete(collection_id)
        self.invalidate(collection_id)

    def invalidate_catalog(self) -> None:
        delete_json(self._catalog_key())

    def invalidate(self, collection_id: str) -> None:
        self.invalidate_catalog()
        self.client.items.invalidate(collection_id)
        self.client.items.invalidate(collection_id, fields=COLLECTION_DETAIL_FIELDS)
        self.client.items.invalidate_list(parent_id=collection_id)
