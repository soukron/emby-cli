"""Tests for the show command."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock

import pytest

from emby_cli.cli import build_parser
from emby_cli.commands import show as show_mod
from emby_cli.commands.show import validate_show_args


def test_show_item_query_parses():
    args = build_parser().parse_args([
        "--server", "http://x", "--api-key", "k",
        "show", "--item", "matrix",
    ])
    assert args.item == "matrix"
    assert args.library is None
    assert validate_show_args(args) is None


def test_show_library_id_parses():
    args = build_parser().parse_args([
        "--server", "http://x", "--api-key", "k",
        "show", "--library", "--id", "lib1",
    ])
    assert args.library == ""
    assert args.id == "lib1"
    assert validate_show_args(args) is None


def test_validate_show_needs_selector():
    args = argparse.Namespace(item="", library=None, id=None, search=None)
    assert validate_show_args(args) == (
        "Provide exactly one of --id or QUERY/--search"
    )


def test_show_item_by_id(capsys):
    client = MagicMock()
    client.get_item_info.return_value = {
        "Id": "abc",
        "Name": "Matrix",
        "Type": "Movie",
        "ProductionYear": 1999,
        "DateCreated": "2024-01-15T10:00:00.0000000Z",
        "Path": "/movies/Matrix.mkv",
        "RunTimeTicks": 8_100_000_000_000,
        "MediaSources": [{"Size": 1024, "Container": "mkv"}],
        "Overview": "A hacker discovers reality.",
        "Genres": ["Action", "Sci-Fi"],
        "CommunityRating": 8.7,
    }
    args = argparse.Namespace(item="", library=None, id="abc", search=None)
    show_mod.cmd_show(client, args)
    out = capsys.readouterr().out
    assert "id: abc" in out
    assert "name: Matrix" in out
    assert "type: Movie" in out
    assert "year: 1999" in out
    assert "added: 2024-01-15 10:00:00" in out
    assert "genres: Action, Sci-Fi" in out
    assert "A hacker discovers reality." in out
    client.get_item_info.assert_called_once()


def test_show_item_disambiguates(capsys):
    client = MagicMock()
    client.search_items.return_value = [
        {"Id": "1", "Name": "Fast", "Type": "Movie", "ProductionYear": 2001},
        {"Id": "2", "Name": "Faster", "Type": "Movie", "ProductionYear": 2003},
    ]
    args = argparse.Namespace(
        item="fast", library=None, id=None, search=None,
    )
    with pytest.raises(SystemExit) as exc:
        show_mod.cmd_show(client, args)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Multiple matches (2)" in out
    assert "emby-cli show --item --id 1" in out
    assert "1" in out and "2" in out
    client.get_item_info.assert_not_called()


def test_show_library_recent(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "lib1", "Name": "PELICULAS", "CollectionType": "movies"},
    ]
    client.get_items.side_effect = [
        {"TotalRecordCount": 42},
        {
            "Items": [
                {
                    "Id": "m1",
                    "Name": "New Movie",
                    "Type": "Movie",
                    "ProductionYear": 2024,
                    "DateCreated": "2024-06-01T12:00:00.0000000Z",
                },
            ],
        },
    ]
    args = argparse.Namespace(
        item=None, library="peliculas", id=None, search=None,
    )
    show_mod.cmd_show(client, args)
    out = capsys.readouterr().out
    assert "name: PELICULAS" in out
    assert "items: 42" in out
    assert "Recently added" in out
    assert "New Movie" in out
    assert "2024-06-01 12:00:00" in out
    # both calls filter to playable media types
    for call in client.get_items.call_args_list:
        assert call.kwargs["item_type"] == "Movie,Episode,Audio"
    recent_call = client.get_items.call_args_list[1]
    assert recent_call.kwargs["sort_by"] == "DateCreated"
    assert recent_call.kwargs["sort_order"] == "Descending"
    assert recent_call.kwargs["limit"] == 10


def test_show_library_disambiguates(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "a", "Name": "Movies", "CollectionType": "movies"},
        {"Id": "b", "Name": "Movies 4K", "CollectionType": "movies"},
    ]
    client.get_items.return_value = {"TotalRecordCount": 1}
    args = argparse.Namespace(
        item=None, library="movies", id=None, search=None,
    )
    with pytest.raises(SystemExit) as exc:
        show_mod.cmd_show(client, args)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Multiple matches (2)" in out
    assert "emby-cli show --library --id a" in out
