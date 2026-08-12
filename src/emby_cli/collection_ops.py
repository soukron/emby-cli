"""Resolution and validation helpers for Emby collections."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from emby_cli.client import EmbyClient

COLLECTION_MEMBER_TYPES = frozenset({"Movie"})


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
