"""Detail renderers shared by canonical item and library commands."""

from __future__ import annotations

import textwrap

from emby_cli.client import EmbyClient
from emby_cli.constants import (
    SHOW_ITEM_FIELDS,
    SHOW_LIBRARY_ITEM_TYPES,
    SHOW_RECENT_COUNT,
)
from emby_cli.resolve import (
    classify_resolution,
    item_label,
    item_video_width,
    sort_for_display,
)
from emby_cli.util import (
    format_duration,
    format_size,
    item_duration_seconds,
    item_remote_size,
)


def _format_emby_date(value: str | None) -> str:
    if not value:
        return "?"
    return value.replace("T", " ")[:19]


def _print_kv(label: str, value: object | None) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text or text == "?":
        return
    print(f"{label}: {text}")


def _print_overview(overview: str | None) -> None:
    if not overview or not overview.strip():
        return
    print("overview:")
    for line in textwrap.wrap(overview.strip(), width=78):
        print(f"  {line}")


def _media_field_value(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "?":
        return None
    return text


def print_media_item(item: dict) -> None:
    """Print the canonical media-item detail view."""
    print("Item")
    _print_kv("id", item.get("Id"))
    _print_kv("name", item_label(item))
    _print_kv("type", item.get("Type"))
    if item.get("Type") == "Episode":
        _print_kv("series", item.get("SeriesName"))
    _print_kv("year", item.get("ProductionYear"))
    _print_kv("status", item.get("Status"))
    child = item.get("ChildCount")
    recursive = item.get("RecursiveItemCount")
    if child is not None:
        _print_kv("children", child)
    if recursive is not None and recursive != child:
        _print_kv("items", recursive)
    print()

    container = item.get("Container")
    if not container:
        sources = item.get("MediaSources") or []
        if sources:
            container = sources[0].get("Container")
    media_rows = [
        ("resolution", _media_field_value(classify_resolution(item_video_width(item)))),
        ("size", _media_field_value(format_size(item_remote_size(item)))),
        ("runtime", _media_field_value(format_duration(item_duration_seconds(item)))),
        ("container", _media_field_value(container)),
        ("path", _media_field_value(item.get("Path"))),
    ]
    useful = [(label, value) for label, value in media_rows if value is not None]
    if useful:
        print("Media")
        for label, value in useful:
            _print_kv(label, value)
        print()

    print("Meta")
    _print_kv("added", _format_emby_date(item.get("DateCreated")))
    genres = item.get("Genres") or []
    if genres:
        _print_kv("genres", ", ".join(str(g) for g in genres))
    rating = item.get("CommunityRating")
    if rating is not None:
        _print_kv("rating", f"{rating:g}")
    _print_kv("official", item.get("OfficialRating"))
    _print_overview(item.get("Overview"))


def _print_recent_items(items: list[dict]) -> None:
    if not items:
        print("(none)")
        return
    items = sort_for_display(items)
    id_w = max(len("ID"), max(len(str(it.get("Id", ""))) for it in items))
    name_w = 40
    header = (
        f"{'ID':<{id_w}}  {'Name':<{name_w}}  {'Type':<8}  "
        f"{'Year':<4}  {'Added':<19}"
    )
    print(header)
    print("-" * len(header))
    for item in items:
        item_id = str(item.get("Id", ""))
        label = item_label(item)
        if len(label) > name_w:
            label = label[: name_w - 1] + "…"
        year = str(item.get("ProductionYear") or "?")
        item_type = str(item.get("Type") or "?")
        added = _format_emby_date(item.get("DateCreated"))
        print(
            f"{item_id:<{id_w}}  {label:<{name_w}}  {item_type:<8}  "
            f"{year:<4}  {added:<19}"
        )


def print_library(client: EmbyClient, library: dict) -> None:
    """Print the canonical library detail view and its recent items."""
    library_id = library.get("Id") or ""
    count_page = client.get_items(
        parent_id=library_id,
        item_type=SHOW_LIBRARY_ITEM_TYPES,
        limit=0,
    )
    total = int(count_page.get("TotalRecordCount") or 0)

    recent_page = client.get_items(
        parent_id=library_id,
        item_type=SHOW_LIBRARY_ITEM_TYPES,
        limit=SHOW_RECENT_COUNT,
        sort_by="DateCreated",
        sort_order="Descending",
        fields=SHOW_ITEM_FIELDS,
    )
    recent = recent_page.get("Items") or []

    print("Library")
    _print_kv("id", library_id)
    _print_kv("name", library.get("Name"))
    _print_kv(
        "type",
        library.get("CollectionType") or library.get("Type") or "Library",
    )
    print()
    print("Content")
    _print_kv("items", total)
    print()
    print(f"Recently added (last {SHOW_RECENT_COUNT})")
    _print_recent_items(recent)
