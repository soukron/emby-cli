"""Tests for search listing and filters."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from emby_cli.commands import search as search_mod
def test_item_count_all_lists_everything(capsys):
    client = MagicMock()
    client.search_items_result.return_value = (
        [
        {"Id": "a", "Name": "A", "Type": "Movie", "ProductionYear": 2020},
        {"Id": "b", "Name": "B", "Type": "Movie", "ProductionYear": 2021},
        ],
        2,
    )
    args = MagicMock(
        count="all",
        id=None,
        search=None,
        item="",
        library=None,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert "Total: 2" in out
    client.search_items_result.assert_called_once_with(
        "",
        item_types="Movie,Episode,Audio,Video",
        limit=None,
    )


def test_item_query_shows_out_of_when_truncated(capsys):
    client = MagicMock()
    client.search_items_result.return_value = (
        [{"Id": str(i), "Name": f"T{i}", "Type": "Movie", "ProductionYear": 2000 + i} for i in range(14)],
        14,
    )
    args = MagicMock(
        count=2,
        id=None,
        search=None,
        item="matrix",
        library=None,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert "Total: 2 (out of 14)" in out
    client.search_items_result.assert_called_once()


def test_item_query_plain_total_when_complete(capsys):
    client = MagicMock()
    client.search_items_result.return_value = (
        [
            {"Id": "1", "Name": "A", "Type": "Movie", "ProductionYear": 1999},
        ],
        1,
    )
    args = MagicMock(
        count=30,
        id=None,
        search=None,
        item="unique",
        library=None,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert "Total: 1" in out
    assert "out of" not in out


def test_library_shows_out_of_when_truncated(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": f"{i}", "Name": f"Lib{i}", "CollectionType": "movies"}
        for i in range(5)
    ]
    args = MagicMock(
        count=2,
        id=None,
        search=None,
        item=None,
        library="Lib",
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert "Total: 2 (out of 5)" in out


def test_item_query_filters_by_type_and_year(capsys):
    client = MagicMock()
    client.search_items_result.return_value = (
        [
            {"Id": "1", "Name": "Spider-Man", "Type": "Movie", "ProductionYear": 2026},
            {"Id": "2", "Name": "Spider-Man", "Type": "Episode", "ProductionYear": 2026},
            {"Id": "3", "Name": "Spider-Man", "Type": "Movie", "ProductionYear": 2024},
        ],
        3,
    )
    args = MagicMock(
        count=20,
        id=None,
        search=None,
        item="spider-man",
        library=None,
        item_type="Movie",
        year=2026,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert "Spider-Man" in out
    assert "Episode" not in out
    assert "2024" not in out
    assert "Total: 1" in out
    client.search_items_result.assert_called_once_with(
        "spider-man",
        item_types="Movie",
        limit=None,
    )


def test_item_query_filters_lowercase_type(capsys):
    client = MagicMock()
    client.search_items_result.return_value = (
        [
            {"Id": "1", "Name": "Spider-Man", "Type": "Movie", "ProductionYear": 2026},
        ],
        1,
    )
    args = MagicMock(
        count="all",
        id=None,
        search=None,
        item="spider-man",
        library=None,
        item_type="movie",
        year=2026,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert "Spider-Man" in out
    client.search_items_result.assert_called_once_with(
        "spider-man",
        item_types="Movie",
        limit=None,
    )


def test_library_count_all_lists_all_libraries(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "1", "Name": "Movies", "CollectionType": "movies"},
        {"Id": "2", "Name": "Series", "CollectionType": "tvshows"},
    ]
    args = MagicMock(
        count="all",
        id=None,
        search=None,
        item=None,
        library="",
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert "Movies" in out
    assert "Series" in out
    assert "Total: 2" in out
