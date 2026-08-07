"""show command — detail view for a media item or library."""

from __future__ import annotations

import argparse
import sys
import textwrap

from emby_cli.client import EmbyClient
from emby_cli.constants import (
    SHOW_ITEM_FIELDS,
    SHOW_ITEM_TYPES,
    SHOW_LIBRARY_ITEM_TYPES,
    SHOW_RECENT_COUNT,
)
from emby_cli.download_ops import find_library
from emby_cli.mode_args import mode_is_item, mode_is_library, resolve_query
from emby_cli.resolve import (
    classify_resolution,
    item_label,
    item_video_width,
    print_item_choices,
    print_library_choices,
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
    query, err = resolve_query(args)
    if err:
        return err
    item_id = (getattr(args, "id", None) or "").strip() or None
    if bool(item_id) == bool(query):
        return "Provide exactly one of --id or QUERY/--search"
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
    if not text:
        return
    print(f"{label}: {text}")


def _print_overview(overview: str | None) -> None:
    if not overview or not overview.strip():
        return
    print("overview:")
    for line in textwrap.wrap(overview.strip(), width=78):
        print(f"  {line}")


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

    print("Media")
    _print_kv("resolution", classify_resolution(item_video_width(item)))
    _print_kv("size", format_size(item_remote_size(item)))
    _print_kv("runtime", format_duration(item_duration_seconds(item)))
    container = item.get("Container")
    if not container:
        sources = item.get("MediaSources") or []
        if sources:
            container = sources[0].get("Container")
    _print_kv("container", container)
    _print_kv("path", item.get("Path"))
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


def _library_rows(client: EmbyClient, libraries: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for lib in libraries:
        page = client.get_items(parent_id=lib["Id"], limit=0)
        rows.append({
            "Id": lib.get("Id", ""),
            "Name": lib.get("Name") or "?",
            "Type": lib.get("CollectionType") or lib.get("Type") or "Library",
            "ItemCount": page.get("TotalRecordCount", 0),
        })
    return rows


def _print_recent_items(items: list[dict]) -> None:
    if not items:
        print("(none)")
        return
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


def _disambiguate_items(matches: list[dict]) -> None:
    print(
        f"Multiple matches ({len(matches)}). "
        "Re-run with --id, for example:\n"
        f'  emby-cli show --item --id {matches[0].get("Id", "<id>")}'
    )
    print_item_choices(matches)


def _disambiguate_libraries(client: EmbyClient, matches: list[dict]) -> None:
    print(
        f"Multiple matches ({len(matches)}). "
        "Re-run with --id, for example:\n"
        f'  emby-cli show --library --id {matches[0].get("Id", "<id>")}'
    )
    print_library_choices(_library_rows(client, matches))


def _cmd_show_item(client: EmbyClient, args: argparse.Namespace) -> None:
    query, _ = resolve_query(args)
    item_id = (getattr(args, "id", None) or "").strip() or None

    if item_id:
        try:
            item = client.get_item_info(item_id, fields=SHOW_ITEM_FIELDS)
        except Exception as exc:
            print(f"error: fetching item {item_id}: {exc}", file=sys.stderr)
            sys.exit(1)
        _print_media_item(item)
        return

    matches = client.search_items(
        query or "",
        item_types=SHOW_ITEM_TYPES,
        limit=30,
    )
    if not matches:
        print("No results.")
        sys.exit(1)
    if len(matches) > 1:
        _disambiguate_items(matches)
        sys.exit(1)

    item = client.get_item_info(matches[0]["Id"], fields=SHOW_ITEM_FIELDS)
    _print_media_item(item)


def _cmd_show_library(client: EmbyClient, args: argparse.Namespace) -> None:
    query, _ = resolve_query(args)
    library_id = (getattr(args, "id", None) or "").strip() or None
    libraries = client.get_libraries()

    if library_id:
        lib = find_library(libraries, library_id=library_id)
        if not lib:
            print(f"Library id '{library_id}' not found. Available:")
            for row in libraries:
                print(f"  - [{row.get('Id', '?')}] {row.get('Name', '?')}")
            sys.exit(1)
        _print_library(client, lib)
        return

    needle = (query or "").lower()
    matches = [
        lib for lib in libraries
        if needle in (lib.get("Name") or "").lower()
    ]
    if not matches:
        print(f"Library '{query}' not found. Available:")
        for row in libraries:
            print(f"  - [{row.get('Id', '?')}] {row.get('Name', '?')}")
        sys.exit(1)
    if len(matches) > 1:
        _disambiguate_libraries(client, matches)
        sys.exit(1)

    _print_library(client, matches[0])


def cmd_show(client: EmbyClient, args: argparse.Namespace) -> None:
    err = validate_show_args(args)
    if err:
        print(err)
        sys.exit(1)

    if mode_is_library(args):
        _cmd_show_library(client, args)
        return
    _cmd_show_item(client, args)
