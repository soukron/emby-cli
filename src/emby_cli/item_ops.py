"""Resolution helpers for playable media items."""

from __future__ import annotations

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


def item_matches_year(item: dict, year: int | None) -> bool:
    if year is None:
        return True
    return item.get("ProductionYear") == year


def filter_items(
    items: list[dict],
    *,
    raw_type: str | None = None,
    year: int | None = None,
) -> list[dict]:
    return [
        item
        for item in items
        if item_matches_type(item, raw_type) and item_matches_year(item, year)
    ]


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
        catalog, _total = client.items.search("", item_types=item_types, use_cache=use_cache)
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

    matches = filter_items(matches, raw_type=raw_type)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ItemResolutionError(f"item {selector} not found")
    raise ItemResolutionError(
        f"item {selector} is ambiguous; use --id",
        matches,
    )
