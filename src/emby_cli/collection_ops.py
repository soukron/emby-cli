"""Resolution, member handling, and download helpers for Emby collections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import DOWNLOADABLE_TYPES
from emby_cli.item_ops import download_items, play_items, playable_items_for_parent
from emby_cli.output import Stats, print_section
from emby_cli.util import safe_output_dir_name

COLLECTION_MEMBER_TYPES = frozenset({"Movie"})

SET_FIELD_ALIASES: dict[str, str] = {
    "year": "ProductionYear",
    "name": "Name",
    "short-name": "SortName",
    "display-order": "DisplayOrder",
    "overview": "Overview",
}

DISPLAY_ORDER_VALUES = frozenset({"premieredate", "sortname"})


class CollectionResolutionError(ValueError):
    """A collection selector was missing, not found, or ambiguous."""

    def __init__(self, message: str, matches: list[dict] | None = None):
        super().__init__(message)
        self.matches = matches or []


@dataclass
class MemberResolution:
    """Valid members and per-reference errors from a batch resolution."""

    items: list[dict]
    errors: list[str]


def match_collections(collections: list[dict], query: str) -> list[dict]:
    """Return collections whose names contain *query*, case-insensitively."""
    needle = query.strip().casefold()
    return [
        collection
        for collection in collections
        if needle in str(collection.get("Name") or "").casefold()
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


def find_collection(
    collections: list[dict],
    *,
    collection_id: str | None = None,
    name: str | None = None,
) -> dict | None:
    """Resolve an exact/unique-prefix ID or a unique exact name."""
    if collection_id:
        matches = _id_matches(collections, collection_id)
        return matches[0] if len(matches) == 1 else None
    if name:
        needle = name.strip().casefold()
        matches = [
            item
            for item in collections
            if str(item.get("Name") or "").casefold() == needle
        ]
        return matches[0] if len(matches) == 1 else None
    return None


def resolve_collection(
    client: EmbyClient,
    *,
    query: str | None = None,
    collection_id: str | None = None,
    use_cache: bool = True,
) -> dict:
    """Resolve one collection or raise an error carrying candidate rows."""
    collections = client.collections.list(use_cache=use_cache)
    if collection_id:
        matches = _id_matches(collections, collection_id)
        selector = f"id '{collection_id}'"
    elif query:
        matches = match_collections(collections, query)
        selector = f"query '{query}'"
    else:
        raise CollectionResolutionError("provide a collection QUERY or --id")

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise CollectionResolutionError(f"collection {selector} not found")
    raise CollectionResolutionError(
        f"collection {selector} is ambiguous; use --id",
        matches,
    )


def parse_set_assignments(assignments: list[str]) -> dict[str, object]:
    """Parse ``KEY=VALUE`` tokens into Emby item field updates."""
    updates: dict[str, object] = {}
    for raw in assignments:
        if "=" not in raw:
            raise ValueError(f"invalid assignment {raw!r}; use KEY=VALUE")
        key, _, value = raw.partition("=")
        alias = key.strip().casefold()
        value = value.strip()
        if not alias:
            raise ValueError(f"invalid assignment {raw!r}; missing field name")
        if not value:
            raise ValueError(f"invalid assignment {raw!r}; value cannot be empty")
        if alias not in SET_FIELD_ALIASES:
            allowed = ", ".join(sorted(SET_FIELD_ALIASES))
            raise ValueError(f"unknown field {key.strip()!r}; allowed: {allowed}")
        emby_key = SET_FIELD_ALIASES[alias]
        if emby_key == "ProductionYear":
            try:
                parsed = int(value)
            except ValueError as exc:
                raise ValueError(f"year must be an integer, got {value!r}") from exc
            updates[emby_key] = parsed
        elif emby_key == "DisplayOrder":
            normalized = value.casefold()
            if normalized not in DISPLAY_ORDER_VALUES:
                allowed = ", ".join(sorted(DISPLAY_ORDER_VALUES))
                raise ValueError(
                    f"display-order must be one of {allowed}, got {value!r}"
                )
            updates[emby_key] = (
                "PremiereDate" if normalized == "premieredate" else "SortName"
            )
        else:
            updates[emby_key] = value
    return updates


def collection_selector_id(args: object) -> str | None:
    """Return a collection ID from parent ``--id`` or subcommand ``--id``."""
    for name in ("id", "collection_id"):
        value = getattr(args, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_item_refs(values: list[str] | None) -> list[str]:
    """Flatten repeated CSV flags and deduplicate while retaining order."""
    refs: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        for part in raw.split(","):
            ref = part.strip()
            if not ref:
                raise ValueError("--item contains an empty ID")
            normalized = ref.casefold()
            if normalized not in seen:
                refs.append(ref)
                seen.add(normalized)
    return refs


def _http_error_message(ref: str, exc: requests.RequestException) -> str:
    response = getattr(exc, "response", None)
    if response is not None and response.status_code == 404:
        return f"item '{ref}' not found"
    return f"could not fetch item '{ref}': {exc}"


def resolve_collection_members(
    client: EmbyClient,
    refs: list[str],
    *,
    allowed_types: frozenset[str] = COLLECTION_MEMBER_TYPES,
) -> MemberResolution:
    """Resolve member IDs independently, retaining valid results on errors."""
    valid: list[dict] = []
    errors: list[str] = []
    prefix_catalog: list[dict] | None = None
    item_types = ",".join(sorted(allowed_types))

    for ref in refs:
        item: dict | None = None
        try:
            item = client.items.get(ref, use_cache=False)
        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            if response is None or response.status_code != 404:
                errors.append(_http_error_message(ref, exc))
                continue
            if prefix_catalog is None:
                try:
                    prefix_catalog = client.items.list_all(
                        item_types=item_types,
                        use_cache=False,
                    )
                except requests.RequestException as catalog_exc:
                    errors.append(_http_error_message(ref, catalog_exc))
                    continue
            matches = _id_matches(prefix_catalog, ref)
            if len(matches) == 1:
                item = matches[0]
            elif len(matches) > 1:
                errors.append(f"item id prefix '{ref}' is ambiguous")
            else:
                errors.append(f"item '{ref}' not found")
            if item is None:
                continue
        except requests.RequestException as exc:
            errors.append(_http_error_message(ref, exc))
            continue

        item_type = str(item.get("Type") or "unknown")
        if item_type not in allowed_types:
            allowed = ", ".join(sorted(allowed_types))
            errors.append(
                f"item '{ref}' has type {item_type}; allowed collection types: {allowed}"
            )
            continue
        valid.append(item)

    return MemberResolution(valid, errors)


def collection_rows(collections: list[dict]) -> list[dict]:
    """Normalize collection objects for list and ambiguity tables."""
    return [
        {
            "Id": item.get("Id") or "",
            "Name": item.get("Name") or "?",
            "Type": "BoxSet",
            "ItemCount": item.get("ItemCount", item.get("ChildCount")),
            "ProductionYear": item.get("ProductionYear"),
        }
        for item in collections
    ]


def collection_downloadable_items(
    client: EmbyClient,
    collection: dict,
    *,
    order_by: str | None = None,
    desc: bool = False,
    use_cache: bool = True,
) -> list[dict]:
    """Return downloadable media items belonging to one collection."""
    collection_id = str(collection.get("Id") or "")
    items = playable_items_for_parent(
        client,
        collection_id,
        order_by=order_by,
        desc=desc,
        use_cache=use_cache,
    )
    return [item for item in items if item.get("Type") in DOWNLOADABLE_TYPES]


def download_collection(
    client: EmbyClient,
    collection: dict,
    output: Path,
    *,
    method: str,
    force: bool,
    throttle: float,
    show_section: bool = True,
    dry_run: bool = False,
    mirror_path: bool = False,
    path_strip: str | None = None,
) -> Stats:
    """Download every downloadable member in *collection* via ``item_ops``."""
    name = collection.get("Name") or "?"
    if show_section:
        print_section(f"Collection: {name}")

    targets = collection_downloadable_items(client, collection, use_cache=False)
    print(f"Found {len(targets)} items in '{name}'")

    dest_dir = output / safe_output_dir_name(name)
    return download_items(
        client,
        targets,
        dest_dir,
        method=method,
        force=force,
        throttle=throttle,
        dry_run=dry_run,
        show_single_progress=True,
        mirror_path=mirror_path,
        path_strip=path_strip,
    )


def play_collection(
    client: EmbyClient,
    collection: dict,
    player_cmd: list[str],
    *,
    wait: bool = False,
    show_section: bool = True,
    order_by: str | None = None,
    desc: bool = False,
) -> int:
    """Play every playable member in *collection* via ``item_ops``."""
    name = collection.get("Name") or "?"
    if show_section:
        print_section(f"Collection: {name}")

    targets = collection_downloadable_items(
        client,
        collection,
        order_by=order_by,
        desc=desc,
        use_cache=True,
    )
    print(f"Found {len(targets)} items in '{name}'")
    return play_items(
        client,
        targets,
        player_cmd,
        wait=wait,
        show_progress=True,
    )
