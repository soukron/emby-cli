"""Resolution and download helpers for Emby library views."""

from __future__ import annotations

from pathlib import Path

from emby_cli.client import EmbyClient
from emby_cli.constants import DOWNLOADABLE_TYPES
from emby_cli.download_ops import find_library, match_libraries
from emby_cli.item_ops import download_items
from emby_cli.output import Stats, print_section
from emby_cli.util import safe_output_dir_name

LIBRARY_TYPE_ALIASES: dict[str, str] = {
    "movies": "movies",
    "movie": "movies",
    "tvshows": "tvshows",
    "tvshow": "tvshows",
    "tv": "tvshows",
    "music": "music",
    "homevideos": "homevideos",
    "homevideo": "homevideos",
    "photos": "photos",
    "photo": "photos",
    "books": "books",
    "book": "books",
    "mixed": "mixed",
}


class LibraryResolutionError(ValueError):
    """A library selector was missing, not found, or ambiguous."""

    def __init__(self, message: str, matches: list[dict] | None = None):
        super().__init__(message)
        self.matches = matches or []


def library_selector_id(args: object) -> str | None:
    """Return a library ID from parent ``--id`` or subcommand ``--id``."""
    for name in ("id", "library_id"):
        value = getattr(args, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def normalize_library_type(raw_type: str | None) -> str | None:
    if not raw_type:
        return None
    return LIBRARY_TYPE_ALIASES.get(raw_type.strip().casefold())


def library_type_value(lib: dict) -> str:
    return str(lib.get("CollectionType") or lib.get("Type") or "").strip().casefold()


def library_matches_type(lib: dict, raw_type: str | None) -> bool:
    normalized = normalize_library_type(raw_type)
    if not normalized:
        return True
    return library_type_value(lib) == normalized


def filter_libraries_by_type(
    libraries: list[dict],
    raw_type: str | None,
) -> list[dict]:
    return [lib for lib in libraries if library_matches_type(lib, raw_type)]


def resolve_library(
    client: EmbyClient,
    *,
    query: str | None = None,
    library_id: str | None = None,
    use_cache: bool = True,
) -> dict:
    """Resolve one library or raise an error carrying candidate rows."""
    libraries = client.libraries.list(use_cache=use_cache)
    if library_id:
        match = find_library(libraries, library_id=library_id)
        selector = f"id '{library_id}'"
        matches = [match] if match else []
    elif query:
        matches = match_libraries(libraries, query)
        selector = f"query '{query}'"
    else:
        raise LibraryResolutionError("provide a library QUERY or --id")

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LibraryResolutionError(f"library {selector} not found")
    raise LibraryResolutionError(
        f"library {selector} is ambiguous; use --id",
        matches,
    )


def library_downloadable_items(client: EmbyClient, library: dict) -> list[dict]:
    """Return downloadable media items belonging to one library view."""
    items = client.get_all_items(parent_id=library["Id"])
    return [item for item in items if item.get("Type") in DOWNLOADABLE_TYPES]


def download_library(
    client: EmbyClient,
    library: dict,
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
    """Download every downloadable item in *library* via ``item_ops``."""
    if show_section:
        print_section(f"Library: {library['Name']}")

    targets = library_downloadable_items(client, library)
    print(f"Found {len(targets)} items in '{library['Name']}'")

    dest_dir = output / safe_output_dir_name(library["Name"])
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
