"""Generic Emby item operations built on the shared client transport."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from emby_cli.constants import ITEM_FIELDS, SEARCH_ITEM_TYPES
from emby_cli.data_cache import delete_json
from emby_cli.media_sort import sort_media_items

if TYPE_CHECKING:
    from emby_cli.client import EmbyClient

ListingDefault = Literal["catalog", "parent"]


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

    def _listing_key(
        self,
        *,
        parent_id: str | None,
        query: str | None,
        item_types: str,
        year: int | None,
        limit: int | None,
        emby_sort: str,
        sort_order: str,
        fields: str | None,
        recursive: bool,
        client_sort: str | None,
        client_desc: bool,
    ) -> str:
        uid = self.client.resolve_user_id()
        query_part = query if query is not None else ""
        year_part = str(year) if year is not None else ""
        limit_part = str(limit) if limit is not None else "all"
        client_part = f"{client_sort}:{'desc' if client_desc else 'asc'}" if client_sort else ""
        return (
            f"v2:item-list:{self.client.server_url}:{uid}:"
            f"{parent_id or ''}:{query_part}:{item_types}:{year_part}:"
            f"{limit_part}:{emby_sort}:{sort_order}:{fields or ITEM_FIELDS}:"
            f"{recursive}:{client_part}"
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
        return self._listing_key(
            parent_id=parent_id,
            query=None,
            item_types=item_types or SEARCH_ITEM_TYPES,
            year=None,
            limit=None,
            emby_sort=sort_by,
            sort_order=sort_order,
            fields=fields,
            recursive=recursive,
            client_sort=None,
            client_desc=False,
        )

    def _search_key(
        self,
        query: str,
        item_types: str,
        *,
        year: int | None = None,
        limit: int | None = None,
        sort_by: str | None = None,
        desc: bool = False,
    ) -> str:
        emby_sort, sort_order, client_sort = self._resolve_list_sort(
            sort_by,
            desc=desc,
            when_unsorted="catalog",
        )
        return self._listing_key(
            parent_id=None,
            query=query,
            item_types=item_types,
            year=year,
            limit=limit,
            emby_sort=emby_sort,
            sort_order=sort_order,
            fields=ITEM_FIELDS,
            recursive=True,
            client_sort=client_sort,
            client_desc=desc,
        )

    @staticmethod
    def _emby_sort_fields(primary: str) -> str:
        """Append ``SortName`` as stable tie-breaker unless already sorting by name."""
        if primary == "SortName" or primary.endswith(",SortName"):
            return primary
        return f"{primary},SortName"

    @staticmethod
    def _emby_sort(
        sort_by: str | None,
        *,
        desc: bool,
    ) -> tuple[str, str]:
        if sort_by == "id":
            return "SortName", "Ascending"
        mapping = {
            "name": "SortName",
            "year": "ProductionYear",
            "release-date": "PremiereDate",
            "added": "DateCreated",
            "resolution": "Resolution",
            "size": "Size",
        }
        emby_sort = ItemsService._emby_sort_fields(mapping.get(sort_by or "", "DateCreated"))
        order = "Descending" if desc else "Ascending"
        if sort_by is None and not desc:
            order = "Descending"
        return emby_sort, order

    @staticmethod
    def _resolve_list_sort(
        sort_by: str | None,
        *,
        desc: bool,
        when_unsorted: ListingDefault,
    ) -> tuple[str, str, str | None]:
        """Return Emby sort, order, and optional client-side re-sort key."""
        if sort_by == "id":
            emby_sort, sort_order = ItemsService._emby_sort("id", desc=desc)
            return emby_sort, sort_order, "id"
        if sort_by:
            emby_sort, sort_order = ItemsService._emby_sort(sort_by, desc=desc)
            return emby_sort, sort_order, None
        if when_unsorted == "parent":
            return "SortName", "Ascending", None
        emby_sort, sort_order = ItemsService._emby_sort(None, desc=desc)
        return emby_sort, sort_order, None

    def _list_items_raw(
        self,
        *,
        parent_id: str | None = None,
        query: str | None = None,
        item_types: str | None = None,
        year: int | None = None,
        limit: int | None = None,
        emby_sort: str,
        sort_order: str,
        fields: str | None = None,
        recursive: bool = True,
        client_sort: str | None = None,
        client_desc: bool = False,
        use_cache: bool = True,
    ) -> tuple[list[dict], int]:
        """Fetch ``/Users/{uid}/Items`` with explicit Emby sort parameters."""
        types = item_types or SEARCH_ITEM_TYPES
        fetch_limit = None if client_sort else limit
        key = self._listing_key(
            parent_id=parent_id,
            query=query,
            item_types=types,
            year=year,
            limit=limit,
            emby_sort=emby_sort,
            sort_order=sort_order,
            fields=fields,
            recursive=recursive,
            client_sort=client_sort,
            client_desc=client_desc,
        )
        if use_cache:
            cached = self.client._cache_read(key)
            if isinstance(cached, dict):
                items = cached.get("items")
                total = cached.get("total")
                if isinstance(items, list) and isinstance(total, int):
                    return items, total

        uid = self.client.resolve_user_id()
        params: dict = {
            "Recursive": str(recursive).lower(),
            "Fields": fields or ITEM_FIELDS,
            "SortBy": emby_sort,
            "SortOrder": sort_order,
        }
        if query is not None:
            params["SearchTerm"] = query
        if parent_id:
            params["ParentId"] = parent_id
        params["IncludeItemTypes"] = types
        if year is not None:
            params["Years"] = str(year)

        items, total = self.client._paginate(
            f"/Users/{uid}/Items",
            params,
            limit=fetch_limit,
        )
        if client_sort:
            items = sort_media_items(items, client_sort, desc=client_desc)
            total = len(items)
            if limit is not None:
                items = items[:limit]

        payload = {"items": items, "total": int(total)}
        if use_cache:
            self.client._cache_write(key, payload)
        return items, int(total)

    def list_items(
        self,
        *,
        query: str = "",
        parent_id: str | None = None,
        item_types: str | None = None,
        year: int | None = None,
        limit: int | None = None,
        sort_by: str | None = None,
        desc: bool = False,
        when_unsorted: ListingDefault = "catalog",
        fields: str | None = None,
        recursive: bool = True,
        use_cache: bool = True,
    ) -> tuple[list[dict], int]:
        """List playable media items with CLI sort keys and optional scope filters."""
        emby_sort, sort_order, client_sort = self._resolve_list_sort(
            sort_by,
            desc=desc,
            when_unsorted=when_unsorted,
        )
        search_term = None if parent_id is not None else query
        return self._list_items_raw(
            parent_id=parent_id,
            query=search_term,
            item_types=item_types,
            year=year,
            limit=limit,
            emby_sort=emby_sort,
            sort_order=sort_order,
            fields=fields,
            recursive=recursive,
            client_sort=client_sort,
            client_desc=desc,
            use_cache=use_cache,
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
        """Return every matching item with explicit Emby ``SortBy`` field names."""
        items, _total = self._list_items_raw(
            parent_id=parent_id,
            query=None,
            item_types=item_types,
            emby_sort=sort_by,
            sort_order=sort_order,
            fields=fields,
            recursive=recursive,
            use_cache=use_cache,
        )
        return items

    def search(
        self,
        query: str = "",
        *,
        item_types: str | None = None,
        year: int | None = None,
        limit: int | None = None,
        sort_by: str | None = None,
        desc: bool = False,
        use_cache: bool = True,
    ) -> tuple[list[dict], int]:
        """Search playable media items via Emby ``SearchTerm`` and filters."""
        return self.list_items(
            query=query,
            item_types=item_types,
            year=year,
            limit=limit,
            sort_by=sort_by,
            desc=desc,
            when_unsorted="catalog",
            use_cache=use_cache,
        )

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

    def merge_and_update(
        self,
        item_id: str,
        updates: dict[str, object],
        *,
        fields: str | None = None,
    ) -> dict:
        """GET one item uncached, merge *updates*, POST the full object back."""
        item = self.get(item_id, fields=fields, use_cache=False)
        for key, value in updates.items():
            item[key] = value
        self.update(item_id, item)
        return item

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
