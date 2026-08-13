"""Client-side sorting helpers for media item rows."""

from __future__ import annotations


def sort_key_id(row: dict) -> tuple[int, int, str]:
    item_id = str(row.get("Id") or "")
    if item_id.isdigit():
        return (0, int(item_id), item_id)
    return (1, 0, item_id.casefold())


def sort_media_items(items: list[dict], order_by: str, *, desc: bool) -> list[dict]:
    """Sort item dicts when Emby cannot (e.g. ``id``) or as a fallback."""
    if order_by == "id":
        return sorted(items, key=sort_key_id, reverse=desc)
    if order_by == "name":
        return sorted(
            items,
            key=lambda row: str(row.get("Name") or "").casefold(),
            reverse=desc,
        )
    if order_by == "year":
        with_year = [row for row in items if row.get("ProductionYear") is not None]
        without_year = [row for row in items if row.get("ProductionYear") is None]
        with_year.sort(
            key=lambda row: (
                int(row.get("ProductionYear") or 0),
                str(row.get("Name") or "").casefold(),
                sort_key_id(row),
            ),
            reverse=desc,
        )
        return with_year + without_year
    if order_by == "release-date":
        with_date = [row for row in items if row.get("PremiereDate")]
        without_date = [row for row in items if not row.get("PremiereDate")]
        with_date.sort(
            key=lambda row: (
                str(row.get("PremiereDate") or ""),
                str(row.get("Name") or "").casefold(),
                sort_key_id(row),
            ),
            reverse=desc,
        )
        return with_date + without_date
    if order_by == "added":
        with_date = [row for row in items if row.get("DateCreated")]
        without_date = [row for row in items if not row.get("DateCreated")]
        with_date.sort(
            key=lambda row: (
                str(row.get("DateCreated") or ""),
                str(row.get("Name") or "").casefold(),
                sort_key_id(row),
            ),
            reverse=desc,
        )
        return with_date + without_date
    return items
