"""Tests for download --library name resolution (substring + disambiguation)."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from emby_cli.commands import download as download_mod
from emby_cli.constants import SHOW_LIBRARY_ITEM_TYPES
from emby_cli.output import Stats


def _library_args(*, library: str | None = None, library_id: str | None = None):
    return argparse.Namespace(
        item=None,
        library=library if library is not None else "",
        id=library_id,
        search=None,
        output="/tmp/out",
        method="download",
        force=False,
        throttle=0,
        dry_run=True,
        pick_best_item=False,
        from_file=None,
    )


def test_download_library_substring_unique(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "a", "Name": "PELICULAS", "CollectionType": "movies"},
        {"Id": "b", "Name": "Series", "CollectionType": "tvshows"},
    ]
    with patch(
        "emby_cli.commands.download.download_library",
        return_value=Stats(),
    ) as mock_dl:
        with pytest.raises(SystemExit) as exc:
            download_mod.cmd_download(client, _library_args(library="peli"))
        assert exc.value.code == 0
    mock_dl.assert_called_once()
    assert mock_dl.call_args.args[1]["Id"] == "a"
    client.get_items.assert_not_called()  # unique → no disambiguation table


def test_download_library_substring_ambiguous(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "a", "Name": "Movies", "CollectionType": "movies"},
        {"Id": "b", "Name": "Movies 4K", "CollectionType": "movies"},
    ]
    client.get_items.return_value = {"TotalRecordCount": 5}
    with pytest.raises(SystemExit) as exc:
        download_mod.cmd_download(client, _library_args(library="movies"))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Multiple matches (2)" in out
    assert "emby-cli download --library --id a" in out
    for call in client.get_items.call_args_list:
        assert call.kwargs["item_type"] == SHOW_LIBRARY_ITEM_TYPES
        assert call.kwargs["limit"] == 0


def test_download_library_substring_missing(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "a", "Name": "Movies", "CollectionType": "movies"},
    ]
    with pytest.raises(SystemExit) as exc:
        download_mod.cmd_download(client, _library_args(library="anime"))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Library 'anime' not found" in out
    assert "Movies" in out
