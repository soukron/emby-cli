"""Item command behavior and observable CLI contracts."""

from __future__ import annotations

from unittest.mock import patch

from emby_cli.cli import build_parser
from emby_cli.client import EmbyClient
from emby_cli.commands.item import cmd_item


def _client() -> EmbyClient:
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    return client


def _args(*values: str):
    return build_parser().parse_args(["item", *values])


def test_item_search_output_and_count(capsys):
    client = _client()
    items = [
        {"Id": "1", "Name": "Alpha", "Type": "Movie", "ProductionYear": 2000},
        {"Id": "2", "Name": "Beta", "Type": "Movie", "ProductionYear": 2010},
    ]
    with patch.object(client.items, "search", return_value=(items, 2)) as search:
        cmd_item(client, _args("search", "a", "--count", "1", "--order-by", "year", "--desc"))
    out = capsys.readouterr().out
    assert "Beta" in out
    assert "Alpha" not in out
    assert "Total: 1 (out of 2)" in out
    search.assert_called_once_with("a", item_types="Movie,Episode,Audio,Video", use_cache=True)


def test_item_list_shows_all_without_count_cap(capsys):
    client = _client()
    items = [
        {"Id": "1", "Name": "Alpha", "Type": "Movie", "ProductionYear": 2000},
        {"Id": "2", "Name": "Beta", "Type": "Movie", "ProductionYear": 2010},
    ]
    with patch.object(client.items, "search", return_value=(items, 2)) as search:
        cmd_item(client, _args("list"))
    out = capsys.readouterr().out
    assert "Alpha" in out
    assert "Beta" in out
    assert "Total: 2" in out
    assert "out of" not in out
    search.assert_called_once_with("", item_types="Movie,Episode,Audio,Video", use_cache=True)


def test_item_show_delegates_to_print_media_item():
    client = _client()
    item = {"Id": "100", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 1999}
    with (
        patch("emby_cli.commands.item.resolve_item", return_value=item) as resolve,
        patch("emby_cli.commands.item._print_media_item") as print_item,
    ):
        cmd_item(client, _args("show", "Matrix"))
    resolve.assert_called_once()
    print_item.assert_called_once_with(item)


def test_item_search_filters_by_type(capsys):
    client = _client()
    items = [
        {"Id": "1", "Name": "Song", "Type": "Audio", "ProductionYear": 2020},
        {"Id": "2", "Name": "Movie", "Type": "Movie", "ProductionYear": 2020},
    ]
    with patch.object(client.items, "search", return_value=(items, 2)) as search:
        cmd_item(client, _args("search", "--type", "audio", "--count", "all"))
    out = capsys.readouterr().out
    assert "Song" in out
    assert "Movie" not in out
    search.assert_called_once_with("", item_types="Audio", use_cache=True)
