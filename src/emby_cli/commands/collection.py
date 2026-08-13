"""Manage Emby BoxSet collections."""

from __future__ import annotations

import argparse
import sys
import textwrap

from emby_cli.api.collections import COLLECTION_DETAIL_FIELDS
from emby_cli.client import EmbyClient
from emby_cli.collection_ops import (
    COLLECTION_MEMBER_TYPES,
    CollectionResolutionError,
    collection_rows,
    collection_selector_id,
    parse_item_refs,
    parse_set_assignments,
    resolve_collection,
    resolve_collection_members,
)
from emby_cli.constants import SEARCH_COUNT_DEFAULT
from emby_cli.output import Stats, print_done, print_error
from emby_cli.resolve import sort_for_display


def _text(args: argparse.Namespace, name: str) -> str | None:
    value = getattr(args, name, None)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _parse_set_rest(rest: list[str] | None) -> tuple[str | None, list[str]]:
    """Split optional collection QUERY from KEY=VALUE assignments."""
    tokens = [part.strip() for part in (rest or []) if part.strip()]
    if not tokens:
        return None, []
    if "=" in tokens[0]:
        return None, tokens
    if len(tokens) == 1:
        return tokens[0], []
    return tokens[0], tokens[1:]


def _set_args(args: argparse.Namespace) -> tuple[str | None, list[str]]:
    query, assignments = _parse_set_rest(getattr(args, "rest", None))
    return query, assignments


def _parse_count(value: object) -> int | None:
    text = str(value).strip().casefold()
    if text == "all":
        return None
    count = int(text)
    if count < 1:
        raise ValueError("--count must be >= 1")
    return count


def validate_collection_args(args: argparse.Namespace) -> str | None:
    """Validate collection arguments without opening a server connection."""
    command = getattr(args, "collection_command", None)
    if command == "search":
        try:
            _parse_count(getattr(args, "count", SEARCH_COUNT_DEFAULT))
        except (TypeError, ValueError) as exc:
            return str(exc) if str(exc).startswith("--count") else "--count must be N or all"
        return None
    if command == "create":
        if not _text(args, "name"):
            return "provide a collection name"
    elif command == "set":
        query, assignments = _set_args(args)
        collection_id = collection_selector_id(args)
        if bool(query) == bool(collection_id):
            return "provide exactly one collection QUERY or --id"
        if not assignments:
            return "provide at least one KEY=VALUE assignment"
        try:
            parse_set_assignments(assignments)
        except ValueError as exc:
            return str(exc)
    elif command in {"show", "delete", "rename", "add-item", "remove-item"}:
        query = _text(args, "query")
        collection_id = collection_selector_id(args)
        if bool(query) == bool(collection_id):
            return "provide exactly one collection QUERY or --id"
    else:
        return "provide a collection subcommand"

    if command == "rename":
        if not _text(args, "new_name"):
            return "provide a new collection name"
        if getattr(args, "short_name", None) is not None and not _text(args, "short_name"):
            return "--short-name cannot be empty"

    if command in {"create", "add-item", "remove-item"}:
        try:
            refs = parse_item_refs(getattr(args, "items", None))
        except ValueError as exc:
            return str(exc)
        if command in {"add-item", "remove-item"} and not refs:
            return "provide at least one --item ID"
    return None


def _sort_key_id(row: dict) -> tuple[int, int, str]:
    item_id = str(row.get("Id") or "")
    if item_id.isdigit():
        return (0, int(item_id), item_id)
    return (1, 0, item_id.casefold())


def _sort_collections(rows: list[dict], order_by: str | None, desc: bool) -> list[dict]:
    if not order_by:
        return sort_for_display(rows)
    if order_by == "name":
        return sorted(
            rows,
            key=lambda row: str(row.get("Name") or "").casefold(),
            reverse=desc,
        )
    if order_by == "id":
        return sorted(rows, key=_sort_key_id, reverse=desc)
    if order_by == "items":
        return sorted(
            rows,
            key=lambda row: (
                int(row["ItemCount"]) if row.get("ItemCount") is not None else -1
            ),
            reverse=desc,
        )
    return sorted(
        rows,
        key=lambda row: (
            int(row["ProductionYear"])
            if row.get("ProductionYear") is not None
            else -1
        ),
        reverse=desc,
    )


def _print_collections(collections: list[dict], *, sort_rows: bool = True) -> None:
    rows = collection_rows(collections)
    if sort_rows:
        rows = sort_for_display(rows)
    if not rows:
        return
    id_width = max(len("ID"), *(len(str(row["Id"])) for row in rows))
    name_width = 44
    header = (
        f"{'ID':<{id_width}}  {'Name':<{name_width}}  "
        f"{'Items':>5}  {'Year':<4}"
    )
    print()
    print(header)
    print("-" * len(header))
    for row in rows:
        name = str(row["Name"])
        if len(name) > name_width:
            name = name[: name_width - 1] + "…"
        count = row.get("ItemCount")
        year = row.get("ProductionYear")
        print(
            f"{str(row['Id']):<{id_width}}  {name:<{name_width}}  "
            f"{str(count if count is not None else '?'):>5}  "
            f"{str(year if year is not None else '?'):<4}"
        )


def _print_members(items: list[dict]) -> None:
    if not items:
        print("(none)")
        return
    items = sort_for_display(items)
    id_width = max(len("ID"), *(len(str(item.get("Id") or "")) for item in items))
    name_width = 44
    type_width = max(len("Type"), *(len(str(item.get("Type") or "?")) for item in items))
    header = (
        f"{'ID':<{id_width}}  {'Name':<{name_width}}  "
        f"{'Type':<{type_width}}  {'Year':<4}"
    )
    print(header)
    print("-" * len(header))
    for item in items:
        name = str(item.get("Name") or "?")
        if len(name) > name_width:
            name = name[: name_width - 1] + "…"
        print(
            f"{str(item.get('Id') or ''):<{id_width}}  {name:<{name_width}}  "
            f"{str(item.get('Type') or '?'):<{type_width}}  "
            f"{str(item.get('ProductionYear') or '?'):<4}"
        )


def _print_resolution_error(exc: CollectionResolutionError) -> None:
    print_error(str(exc))
    if exc.matches:
        _print_collections(exc.matches)


def _resolve_from_args(
    client: EmbyClient,
    args: argparse.Namespace,
    *,
    use_cache: bool,
    query: str | None = None,
) -> dict:
    try:
        return resolve_collection(
            client,
            query=query if query is not None else _text(args, "query"),
            collection_id=collection_selector_id(args),
            use_cache=use_cache,
        )
    except CollectionResolutionError as exc:
        _print_resolution_error(exc)
        raise SystemExit(1) from None


def _resolve_members(client: EmbyClient, args: argparse.Namespace) -> tuple[list[str], int]:
    refs = parse_item_refs(getattr(args, "items", None))
    result = resolve_collection_members(
        client,
        refs,
        allowed_types=COLLECTION_MEMBER_TYPES,
    )
    for message in result.errors:
        print_error(message)
    return [str(item.get("Id") or "") for item in result.items], len(result.errors)


def _cmd_search(client: EmbyClient, args: argparse.Namespace) -> None:
    query = _text(args, "query") or ""
    collections = client.collections.search(
        query,
        use_cache=True,
    )
    rows = collection_rows(collections)
    rows = _sort_collections(
        rows,
        _text(args, "order_by"),
        bool(getattr(args, "desc", False)),
    )
    count = _parse_count(getattr(args, "count", SEARCH_COUNT_DEFAULT))
    shown = rows if count is None else rows[:count]
    if not shown:
        print("No results.")
        return
    _print_collections(shown, sort_rows=False)
    if len(shown) < len(rows):
        print(f"\nTotal: {len(shown)} (out of {len(rows)})\n")
    else:
        print(f"\nTotal: {len(shown)}\n")


def _print_overview(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        return
    print("overview:")
    for line in textwrap.wrap(value.strip(), width=78):
        print(f"  {line}")


def _cmd_show(client: EmbyClient, args: argparse.Namespace) -> None:
    collection = _resolve_from_args(client, args, use_cache=True)
    collection_id = str(collection.get("Id") or "")
    detail = client.items.get(
        collection_id,
        fields=COLLECTION_DETAIL_FIELDS,
        use_cache=True,
    )
    members = client.items.list_all(parent_id=collection_id, use_cache=True)

    print("Collection")
    print(f"id: {collection_id}")
    print(f"name: {detail.get('Name') or collection.get('Name') or '?'}")
    if detail.get("SortName"):
        print(f"short name: {detail['SortName']}")
    if detail.get("ProductionYear") is not None:
        print(f"year: {detail['ProductionYear']}")
    if detail.get("DisplayOrder"):
        print(f"display order: {detail['DisplayOrder']}")
    print(f"items: {len(members)}")
    _print_overview(detail.get("Overview"))
    print("\nMembers")
    _print_members(members)


def _cmd_create(client: EmbyClient, args: argparse.Namespace) -> None:
    item_ids: list[str] = []
    errors = 0
    if getattr(args, "items", None):
        item_ids, errors = _resolve_members(client, args)
    result = client.collections.create(_text(args, "name") or "", item_ids=item_ids)
    print(f"Created collection [{result.get('Id', '?')}] {result.get('Name') or '?'}")
    if errors:
        print_done(Stats(ok=len(item_ids), error=errors))
        raise SystemExit(1)


def _cmd_delete(client: EmbyClient, args: argparse.Namespace) -> None:
    collection = _resolve_from_args(client, args, use_cache=False)
    collection_id = str(collection.get("Id") or "")
    detail = client.items.get(collection_id, use_cache=False)
    if detail.get("Type") != "BoxSet":
        print_error(
            f"refusing to delete item {collection_id}: expected BoxSet, "
            f"got {detail.get('Type') or 'unknown'}"
        )
        raise SystemExit(1)

    name = detail.get("Name") or collection.get("Name") or "?"
    if not bool(getattr(args, "yes", False)):
        if not sys.stdin.isatty():
            print_error("delete requires interactive confirmation; pass --yes to continue")
            raise SystemExit(1)
        try:
            answer = input(f"Delete collection [{collection_id}] {name}? [y/N] ")
        except EOFError:
            print_error("delete confirmation unavailable; pass --yes to continue")
            raise SystemExit(1) from None
        if answer.strip().casefold() not in {"y", "yes"}:
            print("Cancelled.")
            return

    client.collections.delete(collection_id)
    print(f"Deleted collection [{collection_id}] {name}; member media was not deleted.")


def _cmd_rename(client: EmbyClient, args: argparse.Namespace) -> None:
    collection = _resolve_from_args(client, args, use_cache=False)
    collection_id = str(collection.get("Id") or "")
    detail = client.items.get(collection_id, use_cache=False)
    if detail.get("Type") != "BoxSet":
        print_error(f"item {collection_id} is not a BoxSet")
        raise SystemExit(1)
    detail["Name"] = _text(args, "new_name")
    if getattr(args, "short_name", None) is not None:
        detail["SortName"] = _text(args, "short_name")
    client.items.update(collection_id, detail)
    client.collections.invalidate(collection_id)
    message = f"Renamed collection [{collection_id}] to {detail['Name']}"
    if getattr(args, "short_name", None) is not None:
        message += f" (short name: {detail['SortName']})"
    print(message)


def _cmd_set(client: EmbyClient, args: argparse.Namespace) -> None:
    query, assignments = _set_args(args)
    collection = _resolve_from_args(client, args, use_cache=False, query=query)
    collection_id = str(collection.get("Id") or "")
    detail = client.items.get(collection_id, use_cache=False)
    if detail.get("Type") != "BoxSet":
        print_error(f"item {collection_id} is not a BoxSet")
        raise SystemExit(1)
    updates = parse_set_assignments(assignments)
    client.items.merge_and_update(collection_id, updates)
    client.collections.invalidate(collection_id)
    changed = ", ".join(
        f"{alias}={updates[field]!r}"
        for alias, field in (
            ("year", "ProductionYear"),
            ("name", "Name"),
            ("short-name", "SortName"),
            ("display-order", "DisplayOrder"),
            ("overview", "Overview"),
        )
        if field in updates
    )
    print(f"Updated collection [{collection_id}] {changed}")


def _cmd_members(client: EmbyClient, args: argparse.Namespace, *, remove: bool) -> None:
    collection = _resolve_from_args(client, args, use_cache=False)
    collection_id = str(collection.get("Id") or "")
    item_ids, errors = _resolve_members(client, args)
    if item_ids:
        if remove:
            client.collections.remove_items(collection_id, item_ids)
        else:
            client.collections.add_items(collection_id, item_ids)
    print_done(Stats(ok=len(item_ids), error=errors))
    if errors:
        raise SystemExit(1)


def cmd_collection(client: EmbyClient, args: argparse.Namespace) -> None:
    """Validate and dispatch a nested collection command."""
    error = validate_collection_args(args)
    if error:
        print_error(error)
        raise SystemExit(1)
    client.no_data_cache = bool(getattr(args, "no_cache", False))
    command = args.collection_command
    handlers = {
        "search": _cmd_search,
        "show": _cmd_show,
        "create": _cmd_create,
        "delete": _cmd_delete,
        "rename": _cmd_rename,
        "set": _cmd_set,
    }
    if command == "add-item":
        _cmd_members(client, args, remove=False)
    elif command == "remove-item":
        _cmd_members(client, args, remove=True)
    else:
        handlers[command](client, args)
