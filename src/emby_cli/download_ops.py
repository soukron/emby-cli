"""Library name/id matching helpers for search, show, and legacy download."""

from __future__ import annotations

from emby_cli.client import EmbyClient
from emby_cli.constants import SHOW_LIBRARY_ITEM_TYPES


def match_libraries(libraries: list[dict], query: str) -> list[dict]:
    """Return libraries whose Name contains *query* (case-insensitive substring)."""
    needle = (query or "").lower()
    return [
        lib for lib in libraries
        if needle in (lib.get("Name") or "").lower()
    ]


def library_rows(
    client: EmbyClient,
    libraries: list[dict],
    *,
    item_types: str = SHOW_LIBRARY_ITEM_TYPES,
) -> list[dict]:
    """Build choice-table rows with ItemCount filtered like ``show --library``."""
    rows: list[dict] = []
    for lib in libraries:
        page = client.get_items(
            parent_id=lib["Id"],
            item_type=item_types,
            limit=0,
        )
        rows.append({
            "Id": lib.get("Id", ""),
            "Name": lib.get("Name") or "?",
            "Type": lib.get("CollectionType") or lib.get("Type") or "Library",
            "ItemCount": page.get("TotalRecordCount", 0),
        })
    return rows


def find_library(
    libraries: list[dict],
    *,
    library_id: str | None = None,
    name: str | None = None,
) -> dict | None:
    """Resolve one library view by Id (exact or unique prefix) or by unique name.

    Name match is case-insensitive exact. Zero or multiple matches → None.
    Prefer ``match_libraries`` for QUERY name resolution (substring).
    """
    if library_id:
        needle = library_id.strip()
        exact = [lib for lib in libraries if str(lib.get("Id", "")) == needle]
        if len(exact) == 1:
            return exact[0]
        if not exact and needle:
            prefixes = [
                lib for lib in libraries
                if str(lib.get("Id", "")).lower().startswith(needle.lower())
            ]
            if len(prefixes) == 1:
                return prefixes[0]
        return None

    if name:
        matches = [
            lib for lib in libraries
            if (lib.get("Name") or "").lower() == name.lower()
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    return None
