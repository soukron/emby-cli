"""Library matching and resolution helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from emby_cli.client import EmbyClient
from emby_cli.library_ops import (
    LibraryResolutionError,
    download_library,
    filter_libraries_by_type,
    library_matches_type,
    normalize_library_type,
    resolve_library,
)
from emby_cli.output import Stats

LIBRARIES = [
    {"Id": "100", "Name": "Películas", "CollectionType": "movies"},
    {"Id": "200", "Name": "Series", "CollectionType": "tvshows"},
    {"Id": "300", "Name": "Música", "CollectionType": "music"},
]


def _client() -> EmbyClient:
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    return client


def test_normalize_library_type_aliases():
    assert normalize_library_type("movie") == "movies"
    assert normalize_library_type("TV") == "tvshows"
    assert normalize_library_type("unknown") is None


def test_library_matches_type():
    lib = LIBRARIES[0]
    assert library_matches_type(lib, "movies")
    assert library_matches_type(lib, "movie")
    assert not library_matches_type(lib, "tvshows")


def test_filter_libraries_by_type():
    filtered = filter_libraries_by_type(LIBRARIES, "tv")
    assert filtered == [LIBRARIES[1]]


def test_resolve_library_reports_ambiguous_candidates():
    client = _client()
    with patch.object(client.libraries, "list", return_value=LIBRARIES) as listing:
        with pytest.raises(LibraryResolutionError) as exc_info:
            resolve_library(client, query="e", use_cache=False)
    assert len(exc_info.value.matches) == 2
    assert "ambiguous" in str(exc_info.value)
    listing.assert_called_once_with(use_cache=False)


def test_resolve_library_by_id_prefix():
    client = _client()
    with patch.object(client.libraries, "list", return_value=LIBRARIES):
        assert resolve_library(client, library_id="20", use_cache=False) == LIBRARIES[1]


def test_download_library_uses_named_output_subdir():
    client = _client()
    library = LIBRARIES[0]
    items = [{"Id": "1", "Name": "Film", "Type": "Movie", "Path": "/media/Film.mkv"}]
    with (
        patch.object(client, "get_all_items", return_value=items),
        patch("emby_cli.library_ops.download_items", return_value=Stats(ok=1)) as download_items,
    ):
        download_library(
            client,
            library,
            Path("/out"),
            method="download",
            force=False,
            throttle=0,
            show_section=False,
        )
    assert download_items.call_args.args[2] == Path("/out/Películas")
