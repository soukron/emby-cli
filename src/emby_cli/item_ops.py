"""Resolution and listing helpers for playable media items."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import SEARCH_ITEM_TYPES, SHOW_ITEM_FIELDS

ITEM_TYPE_ALIASES: dict[str, str] = {
    "movie": "Movie",
    "movies": "Movie",
    "episode": "Episode",
    "episodes": "Episode",
    "audio": "Audio",
    "music": "Audio",
    "video": "Video",
    "videos": "Video",
}


class ItemResolutionError(ValueError):
    """A media item selector was missing, not found, or ambiguous."""

    def __init__(self, message: str, matches: list[dict] | None = None):
        super().__init__(message)
        self.matches = matches or []


@dataclass(frozen=True)
class ItemListingQuery:
    """Parameters for a server-side item listing request."""

    query: str
    item_types: str
    year: int | None
    api_limit: int | None
    api_sort: str | None
    desc: bool


def item_selector_id(args: object) -> str | None:
    """Return an item ID from parent ``--id`` or subcommand ``--id``."""
    for name in ("id", "item_id"):
        value = getattr(args, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def normalize_item_type(raw_type: str | None) -> str | None:
    if not raw_type:
        return None
    return ITEM_TYPE_ALIASES.get(raw_type.strip().casefold())


def item_types_for_api(raw_type: str | None) -> str:
    normalized = normalize_item_type(raw_type)
    return normalized or SEARCH_ITEM_TYPES


def item_matches_type(item: dict, raw_type: str | None) -> bool:
    normalized = normalize_item_type(raw_type)
    if not normalized:
        return True
    return item.get("Type") == normalized


def build_item_listing_query(
    *,
    query: str = "",
    raw_type: str | None = None,
    year: int | None = None,
    count: int | None = None,
    order_by: str | None = None,
    desc: bool = False,
) -> ItemListingQuery:
    """Build a listing query delegated to Emby (filters, sort, pagination)."""
    return ItemListingQuery(
        query=query,
        item_types=item_types_for_api(raw_type),
        year=year,
        api_limit=None if count is None else count,
        api_sort=order_by,
        desc=desc,
    )


def fetch_item_listing(
    client: EmbyClient,
    listing: ItemListingQuery,
    *,
    use_cache: bool = True,
) -> tuple[list[dict], int]:
    """Fetch one item listing page from Emby."""
    items, total = client.items.search(
        listing.query,
        item_types=listing.item_types,
        year=listing.year,
        limit=listing.api_limit,
        sort_by=listing.api_sort,
        desc=listing.desc,
        use_cache=use_cache,
    )
    return items, total


def _id_matches(items: list[dict], item_id: str) -> list[dict]:
    needle = item_id.strip().casefold()
    exact = [item for item in items if str(item.get("Id") or "").casefold() == needle]
    if exact:
        return exact
    return [
        item
        for item in items
        if str(item.get("Id") or "").casefold().startswith(needle)
    ]


def resolve_item(
    client: EmbyClient,
    *,
    query: str | None = None,
    item_id: str | None = None,
    raw_type: str | None = None,
    use_cache: bool = True,
) -> dict:
    """Resolve one media item or raise an error carrying candidate rows."""
    item_types = item_types_for_api(raw_type)
    if item_id:
        try:
            item = client.items.get(
                item_id,
                fields=SHOW_ITEM_FIELDS,
                use_cache=use_cache,
            )
            if item_matches_type(item, raw_type):
                return item
            raise ItemResolutionError(f"item id '{item_id}' not found")
        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            if response is None or response.status_code != 404:
                raise
        catalog, _total = client.items.search(
            "",
            item_types=item_types,
            use_cache=use_cache,
        )
        matches = _id_matches(catalog, item_id)
        selector = f"id '{item_id}'"
    elif query:
        matches, _total = client.items.search(
            query,
            item_types=item_types,
            use_cache=use_cache,
        )
        selector = f"query '{query}'"
    else:
        raise ItemResolutionError("provide a media item QUERY or --id")

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ItemResolutionError(f"item {selector} not found")
    raise ItemResolutionError(
        f"item {selector} is ambiguous; use --id",
        matches,
    )
