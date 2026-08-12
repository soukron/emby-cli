"""Generic Emby item operations built on the shared client transport."""

from __future__ import annotations

from typing import TYPE_CHECKING

from emby_cli.constants import ITEM_FIELDS
from emby_cli.data_cache import delete_json

if TYPE_CHECKING:
    from emby_cli.client import EmbyClient


class ItemsService:
    """Read and mutate generic ``/Items`` resources."""

    def __init__(self, client: EmbyClient):
        self.client = client

    def _key(self, item_id: str, fields: str | None) -> str:
        uid = self.client.resolve_user_id()
        return (
            f"v2:item:{self.client.server_url}:{uid}:"
            f"{item_id}:{fields or 'all'}"
        )

    def _list_key(
        self,
        *,
        parent_id: str | None,
        item_types: str | None,
        fields: str | None,
        recursive: bool,
        sort_by: str,
        sort_order: str,
    ) -> str:
        uid = self.client.resolve_user_id()
        return (
            f"v2:items:{self.client.server_url}:{uid}:"
            f"{parent_id or ''}:{item_types or ''}:{fields or ITEM_FIELDS}:"
            f"{recursive}:{sort_by}:{sort_order}"
        )

    def list_all(
        self,
        *,
        parent_id: str | None = None,
        item_types: str | None = None,
        fields: str | None = None,
        recursive: bool = True,
        sort_by: str = "SortName",
        sort_order: str = "Ascending",
        use_cache: bool = True,
    ) -> list[dict]:
        """Return every matching item, following Emby's pagination."""
        uid = self.client.resolve_user_id()
        key = self._list_key(
            parent_id=parent_id,
            item_types=item_types,
            fields=fields,
            recursive=recursive,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        if use_cache:
            cached = self.client._cache_read(key)
            if isinstance(cached, list):
                return cached

        params: dict = {
            "Recursive": str(recursive).lower(),
            "Fields": fields or ITEM_FIELDS,
            "SortBy": sort_by,
            "SortOrder": sort_order,
        }
        if parent_id:
            params["ParentId"] = parent_id
        if item_types:
            params["IncludeItemTypes"] = item_types
        items, _total = self.client._paginate(f"/Users/{uid}/Items", params)
        if use_cache:
            self.client._cache_write(key, items)
        return items

    def get(
        self,
        item_id: str,
        *,
        fields: str | None = None,
        use_cache: bool = True,
    ) -> dict:
        """Get one item for the current user."""
        uid = self.client.resolve_user_id()
        key = self._key(item_id, fields)
        if use_cache:
            cached = self.client._cache_read(key)
            if isinstance(cached, dict):
                return cached
        params = {"Fields": fields} if fields else None
        data = self.client._get(
            f"/Users/{uid}/Items/{item_id}",
            params=params,
        ).json()
        if use_cache:
            self.client._cache_write(key, data)
        return data

    def update(self, item_id: str, item: dict) -> None:
        """Update an item with the complete object returned by Emby."""
        self.client._post(f"/Items/{item_id}", item)
        self.invalidate(item_id)

    def delete(self, item_id: str) -> None:
        """Delete one item using Emby's generic destructive endpoint."""
        self.client._delete(f"/Items/{item_id}")
        self.invalidate(item_id)

    def invalidate(self, item_id: str, *, fields: str | None = None) -> None:
        delete_json(self._key(item_id, fields))

    def invalidate_list(
        self,
        *,
        parent_id: str | None = None,
        item_types: str | None = None,
        fields: str | None = None,
        recursive: bool = True,
        sort_by: str = "SortName",
        sort_order: str = "Ascending",
    ) -> None:
        delete_json(self._list_key(
            parent_id=parent_id,
            item_types=item_types,
            fields=fields,
            recursive=recursive,
            sort_by=sort_by,
            sort_order=sort_order,
        ))
