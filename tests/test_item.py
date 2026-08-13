"""Item command behavior and observable CLI contracts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from emby_cli.cli import build_parser
from emby_cli.client import EmbyClient
from emby_cli.commands.item import cmd_item
from emby_cli.output import Stats


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
    with patch.object(client.items, "list_items", return_value=(items, 2)) as list_items:
        cmd_item(client, _args("search", "a", "--count", "1", "--order-by", "year", "--desc"))
    out = capsys.readouterr().out
    assert "Beta" in out
    assert "Alpha" not in out
    assert "Total: 1 (out of 2)" in out
    list_items.assert_called_once_with(
        query="a",
        parent_id=None,
        item_types="Movie,Episode,Audio,Video",
        year=None,
        limit=None,
        sort_by="year",
        desc=True,
        when_unsorted="catalog",
        use_cache=True,
    )


def test_item_search_strict_by_default(capsys):
    client = _client()
    matrix = {"Id": "100", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 1999}
    with patch.object(client.items, "list_items", return_value=([matrix], 1)) as list_items:
        cmd_item(client, _args("search", "Matrix", "--type", "movie"))
    assert "The Matrix" in capsys.readouterr().out
    list_items.assert_called_once_with(
        query="Matrix",
        parent_id=None,
        item_types="Movie",
        year=None,
        limit=None,
        sort_by=None,
        desc=False,
        when_unsorted="catalog",
        use_cache=True,
    )


def test_item_search_parses_title_line_year_with_flag(capsys):
    client = _client()
    matrix = {"Id": "100", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 1999}
    with patch.object(client.items, "list_items", return_value=([matrix], 1)) as list_items:
        cmd_item(client, _args("search", "Matrix (1999)", "--type", "movie", "--parse-query"))
    assert "The Matrix" in capsys.readouterr().out
    list_items.assert_called_once_with(
        query="Matrix",
        parent_id=None,
        item_types="Movie",
        year=1999,
        limit=30,
        sort_by=None,
        desc=False,
        when_unsorted="catalog",
        use_cache=True,
    )


def test_item_search_parses_series_episode_line_with_flag(capsys):
    client = _client()
    episode = {
        "Id": "e1",
        "Name": "Pilot",
        "Type": "Episode",
        "ProductionYear": 2007,
    }
    with patch(
        "emby_cli.commands.item.fetch_item_listing",
        return_value=([episode], 1),
    ) as fetch:
        cmd_item(client, _args("search", "Californication S01E01", "--parse-query"))
    assert "Pilot" in capsys.readouterr().out
    listing = fetch.call_args.args[1]
    assert listing.title_line == "Californication S01E01"


def test_item_list_shows_all_without_count_cap(capsys):
    client = _client()
    items = [
        {"Id": "1", "Name": "Alpha", "Type": "Movie", "ProductionYear": 2000},
        {"Id": "2", "Name": "Beta", "Type": "Movie", "ProductionYear": 2010},
    ]
    with patch.object(client.items, "list_items", return_value=(items, 2)) as list_items:
        cmd_item(client, _args("list"))
    out = capsys.readouterr().out
    assert "Alpha" in out
    assert "Beta" in out
    assert "Total: 2" in out
    assert "out of" not in out
    list_items.assert_called_once_with(
        query="",
        parent_id=None,
        item_types="Movie,Episode,Audio,Video",
        year=None,
        limit=None,
        sort_by=None,
        desc=False,
        when_unsorted="catalog",
        use_cache=True,
    )


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


def test_item_play_launches_player_for_query():
    client = _client()
    item = {"Id": "100", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 1999}
    with (
        patch("emby_cli.commands.item.resolve_title_items", return_value=[item]),
        patch("emby_cli.commands.item.find_player", return_value=["vlc"]),
        patch("emby_cli.commands.item.play_one_item", return_value=0) as play_one,
    ):
        cmd_item(client, _args("play", "Matrix", "--player", "vlc"))
    play_one.assert_called_once_with(client, item, ["vlc"], wait=False)


def test_item_play_launches_player_for_title_line():
    client = _client()
    item = {"Id": "100", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 1999}
    with (
        patch("emby_cli.commands.item.resolve_title_items", return_value=[item]) as resolve,
        patch("emby_cli.commands.item.find_player", return_value=["vlc"]),
        patch("emby_cli.commands.item.play_one_item", return_value=0) as play_one,
    ):
        cmd_item(client, _args("play", "The Matrix (1999)", "--player", "vlc"))
    resolve.assert_called_once()
    play_one.assert_called_once_with(client, item, ["vlc"], wait=False)


def test_item_play_csv_ids_launches_each():
    client = _client()
    with (
        patch("emby_cli.commands.item.find_player", return_value=["vlc"]),
        patch("emby_cli.commands.item.play_item_ids", return_value=0) as play_ids,
    ):
        cmd_item(client, _args("play", "--id", "1,2"))
    play_ids.assert_called_once()


def test_item_download_delegates_to_item_ops():
    client = _client()
    item = {"Id": "100", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 1999}
    with (
        patch("emby_cli.commands.item.resolve_title_items", return_value=[item]),
        patch("emby_cli.commands.item.download_items", return_value=Stats(ok=1)) as download_items,
        patch("emby_cli.commands.item.print_done"),
    ):
        with pytest.raises(SystemExit) as exc:
            cmd_item(client, _args("download", "Matrix", "--dry-run"))
    assert exc.value.code == 0
    download_items.assert_called_once()
    assert download_items.call_args.args[1] == [item]


def test_item_search_filters_by_type(capsys):
    client = _client()
    items = [
        {"Id": "1", "Name": "Song", "Type": "Audio", "ProductionYear": 2020},
        {"Id": "2", "Name": "Movie", "Type": "Movie", "ProductionYear": 2020},
    ]
    with patch.object(client.items, "list_items", return_value=([items[0]], 1)) as list_items:
        cmd_item(client, _args("search", "--type", "audio", "--count", "all"))
    out = capsys.readouterr().out
    assert "Song" in out
    assert "Movie" not in out
    list_items.assert_called_once_with(
        query="",
        parent_id=None,
        item_types="Audio",
        year=None,
        limit=None,
        sort_by=None,
        desc=False,
        when_unsorted="catalog",
        use_cache=True,
    )
