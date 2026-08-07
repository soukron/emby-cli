"""Tests for search --item --all total gate."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from emby_cli.commands import search as search_mod
from emby_cli.constants import SEARCH_COUNT_DEFAULT


def test_item_all_refuses_when_too_many(capsys):
    client = MagicMock()
    client.get_items.return_value = {"TotalRecordCount": SEARCH_COUNT_DEFAULT + 1}
    args = MagicMock(
        count=SEARCH_COUNT_DEFAULT,
        id=None,
        search=None,
        all=True,
        item="",
        library=None,
    )
    with pytest.raises(SystemExit) as exc:
        search_mod.cmd_search(client, args)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert f"There are {SEARCH_COUNT_DEFAULT + 1} media items on this server." in out
    assert "Please narrow the results with a query" in out
    assert 'emby-cli search --item "title"' in out
    client.get_all_items.assert_not_called()


def test_item_all_lists_when_within_limit(capsys):
    client = MagicMock()
    client.get_items.return_value = {"TotalRecordCount": 2}
    client.get_all_items.return_value = [
        {"Id": "a", "Name": "A", "Type": "Movie", "ProductionYear": 2020},
        {"Id": "b", "Name": "B", "Type": "Movie", "ProductionYear": 2021},
    ]
    args = MagicMock(
        count=SEARCH_COUNT_DEFAULT,
        id=None,
        search=None,
        all=True,
        item="",
        library=None,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert "Total: 2" in out
    assert "out of" not in out
    client.get_all_items.assert_called_once()


def test_item_query_shows_out_of_when_truncated(capsys):
    client = MagicMock()
    client.search_items_result.return_value = (
        [
            {"Id": "1", "Name": "A", "Type": "Movie", "ProductionYear": 1999},
            {"Id": "2", "Name": "B", "Type": "Movie", "ProductionYear": 2003},
        ],
        14,
    )
    args = MagicMock(
        count=2,
        id=None,
        search=None,
        all=False,
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
        all=False,
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
    client.get_items.return_value = {"TotalRecordCount": 0}
    args = MagicMock(
        count=2,
        id=None,
        search=None,
        all=True,
        item=None,
        library="",
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert "Total: 2 (out of 5)" in out
