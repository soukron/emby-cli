"""Tests for the show command."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock

import pytest

from emby_cli.cli import build_parser
from emby_cli.commands import show as show_mod
from emby_cli.commands.show import validate_show_args


def test_show_item_id_parses():
    args = build_parser().parse_args([
        "--server", "http://x", "--api-key", "k",
        "show", "--item", "--id", "abc",
    ])
    assert args.item is True
    assert args.library is None
    assert args.id == "abc"
    assert validate_show_args(args) is None


def test_show_library_id_parses():
    args = build_parser().parse_args([
        "--server", "http://x", "--api-key", "k",
        "show", "--library", "--id", "lib1",
    ])
    assert args.library is True
    assert args.id == "lib1"
    assert validate_show_args(args) is None


def test_show_rejects_query_as_item_value():
    parser = build_parser()
    with pytest.raises(SystemExit):
        # --item no longer takes QUERY; "matrix" would be a stray positional
        parser.parse_args([
            "--server", "http://x", "--api-key", "k",
            "show", "--item", "matrix",
        ])


def test_show_requires_id():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--server", "http://x", "--api-key", "k",
            "show", "--item",
        ])


def test_validate_show_needs_id():
    args = argparse.Namespace(item=True, library=None, id=None)
    assert validate_show_args(args) == "Provide --id"


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
    args = argparse.Namespace(item=True, library=None, id="abc")
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
    client.search_items.assert_not_called()


def test_show_omits_empty_media_section(capsys):
    client = MagicMock()
    client.get_item_info.return_value = {
        "Id": "s1",
        "Name": "Some Series",
        "Type": "Series",
        "ProductionYear": 2020,
        "ChildCount": 5,
        "Overview": "A show about things.",
    }
    args = argparse.Namespace(item=True, library=None, id="s1")
    show_mod.cmd_show(client, args)
    out = capsys.readouterr().out
    assert "type: Series" in out
    assert "Media" not in out
    assert "resolution:" not in out
    assert "size:" not in out
    assert "runtime:" not in out
    assert "?" not in out.split("Meta")[0]


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
        item=None, library=True, id="lib1",
    )
    show_mod.cmd_show(client, args)
    out = capsys.readouterr().out
    assert "name: PELICULAS" in out
    assert "items: 42" in out
    assert "Recently added" in out
    assert "New Movie" in out
    assert "2024-06-01 12:00:00" in out
    for call in client.get_items.call_args_list:
        assert call.kwargs["item_type"] == "Movie,Episode,Audio"
    recent_call = client.get_items.call_args_list[1]
    assert recent_call.kwargs["sort_by"] == "DateCreated"
    assert recent_call.kwargs["sort_order"] == "Descending"
    assert recent_call.kwargs["limit"] == 10


def test_show_library_id_not_found(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "a", "Name": "Movies", "CollectionType": "movies"},
    ]
    args = argparse.Namespace(item=None, library=True, id="missing")
    with pytest.raises(SystemExit) as exc:
        show_mod.cmd_show(client, args)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Library id 'missing' not found" in out
    assert "Movies" in out
