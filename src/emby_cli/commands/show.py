"""show command — detail view for a media item or library by --id."""

from __future__ import annotations

import argparse
import sys
import textwrap

import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import (
    SHOW_ITEM_FIELDS,
    SHOW_LIBRARY_ITEM_TYPES,
    SHOW_RECENT_COUNT,
)
from emby_cli.deprecation import warn_deprecated
from emby_cli.download_ops import find_library
from emby_cli.mode_args import mode_is_item, mode_is_library
from emby_cli.resolve import (
    classify_resolution,
    item_label,
    item_video_width,
    print_available_libraries,
    sort_for_display,
)
from emby_cli.util import (
    format_duration,
    format_size,
    item_duration_seconds,
    item_remote_size,
)


def validate_show_args(args: argparse.Namespace) -> str | None:
    """Return an error message if mode/selectors are invalid; else ``None``."""
    if not mode_is_item(args) and not mode_is_library(args):
        return "Specify --item or --library"
    item_id = (getattr(args, "id", None) or "").strip()
    if not item_id:
        return "Provide --id"
    return None


def _format_emby_date(value: str | None) -> str:
    if not value:
        return "?"
    # Emby: "2024-01-15T12:34:56.0000000Z"
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
    """Return a printable media value, or ``None`` if missing / unknown."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "?":
        return None
    return text


def _print_media_item(item: dict) -> None:
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
    for it in items:
        iid = str(it.get("Id", ""))
        label = item_label(it)
        if len(label) > name_w:
            label = label[: name_w - 1] + "…"
        year = str(it.get("ProductionYear") or "?")
        itype = str(it.get("Type") or "?")
        added = _format_emby_date(it.get("DateCreated"))
        print(
            f"{iid:<{id_w}}  {label:<{name_w}}  {itype:<8}  "
            f"{year:<4}  {added:<19}"
        )


def _print_library(client: EmbyClient, lib: dict) -> None:
    lib_id = lib.get("Id") or ""
    count_page = client.get_items(
        parent_id=lib_id,
        item_type=SHOW_LIBRARY_ITEM_TYPES,
        limit=0,
    )
    total = int(count_page.get("TotalRecordCount") or 0)

    recent_page = client.get_items(
        parent_id=lib_id,
        item_type=SHOW_LIBRARY_ITEM_TYPES,
        limit=SHOW_RECENT_COUNT,
        sort_by="DateCreated",
        sort_order="Descending",
        fields=SHOW_ITEM_FIELDS,
    )
    recent = recent_page.get("Items") or []

    print("Library")
    _print_kv("id", lib_id)
    _print_kv("name", lib.get("Name"))
    _print_kv(
        "type",
        lib.get("CollectionType") or lib.get("Type") or "Library",
    )
    print()
    print("Content")
    _print_kv("items", total)
    print()
    print(f"Recently added (last {SHOW_RECENT_COUNT})")
    _print_recent_items(recent)


def _cmd_show_item(client: EmbyClient, args: argparse.Namespace) -> None:
    item_id = (getattr(args, "id", None) or "").strip()
    try:
        item = client.get_item_info(item_id, fields=SHOW_ITEM_FIELDS)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"error: fetching item {item_id}: {exc}", file=sys.stderr)
        sys.exit(1)
    _print_media_item(item)


def _cmd_show_library(client: EmbyClient, args: argparse.Namespace) -> None:
    library_id = (getattr(args, "id", None) or "").strip()
    libraries = client.get_libraries()
    lib = find_library(libraries, library_id=library_id)
    if not lib:
        print(f"Library id '{library_id}' not found. Available:")
        print_available_libraries(libraries)
        sys.exit(1)
    _print_library(client, lib)


def cmd_show(client: EmbyClient, args: argparse.Namespace) -> None:
    warn_deprecated("show")
    err = validate_show_args(args)
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)

    if mode_is_library(args):
        _cmd_show_library(client, args)
        return
    _cmd_show_item(client, args)
