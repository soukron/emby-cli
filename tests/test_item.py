"""Item command behavior and observable CLI contracts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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


def test_item_show_prints_full_detail(capsys):
    client = _client()
    item = {
        "Id": "100",
        "Name": "The Matrix",
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
    with patch("emby_cli.commands.item.resolve_item", return_value=item):
        cmd_item(client, _args("show", "Matrix"))
    out = capsys.readouterr().out
    assert "id: 100" in out
    assert "name: The Matrix" in out
    assert "year: 1999" in out
    assert "added: 2024-01-15 10:00:00" in out
    assert "genres: Action, Sci-Fi" in out
    assert "A hacker discovers reality." in out


def test_item_show_omits_empty_media_section(capsys):
    client = _client()
    item = {
        "Id": "s1",
        "Name": "Some Series",
        "Type": "Series",
        "ProductionYear": 2020,
        "ChildCount": 5,
        "Overview": "A show about things.",
    }
    with patch("emby_cli.commands.item.resolve_item", return_value=item):
        cmd_item(client, _args("show", "Some Series"))
    out = capsys.readouterr().out
    assert "type: Series" in out
    assert "Media" not in out
    assert "resolution:" not in out
    assert "size:" not in out
    assert "runtime:" not in out


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


def test_item_play_csv_ids_launches_each(capsys):
    client = _client()
    items = [
        {"Id": "1", "Name": "A", "Type": "Movie", "ProductionYear": 2001},
        {"Id": "2", "Name": "B", "Type": "Movie", "ProductionYear": 2002},
    ]
    with patch("emby_cli.commands.item.find_player", return_value=["vlc"]), patch.object(
        client,
        "get_item_info",
        side_effect=items,
    ), patch.object(
        client,
        "resolve_direct_stream_url",
        side_effect=["http://u/1", "http://u/2"],
    ), patch("emby_cli.item_ops.play_url", return_value=0) as play_url:
        cmd_item(client, _args("play", "--id", "1,2"))
    assert [call.args[1] for call in play_url.call_args_list] == ["http://u/1", "http://u/2"]
    out = capsys.readouterr().out
    assert "[1/2] Playing: A" in out
    assert "[2/2] Playing: B" in out


def test_item_play_csv_continues_after_fetch_error(capsys):
    client = MagicMock()

    def get_info(item_id):
        if item_id == "bad":
            raise RuntimeError("gone")
        return {"Id": item_id, "Name": "Ok", "Type": "Movie", "ProductionYear": 2000}

    client.get_item_info.side_effect = get_info
    client.resolve_direct_stream_url.return_value = "http://u/ok"
    with patch("emby_cli.commands.item.find_player", return_value=["vlc"]), patch(
        "emby_cli.item_ops.play_url",
        return_value=0,
    ) as play_url, pytest.raises(SystemExit) as exc:
        cmd_item(client, _args("play", "--id", "bad,ok"))
    assert exc.value.code == 1
    assert play_url.call_count == 1
    captured = capsys.readouterr()
    assert "fetching item bad" in captured.err
    assert "Playing: Ok" in captured.out


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


def test_item_search_count_all_is_distinct_from_list(capsys):
    client = _client()
    item = {"Id": "1", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 1999}
    with patch.object(client.items, "list_items", return_value=([item], 1)) as list_items:
        cmd_item(client, _args("search", "Matrix", "--count", "all"))
    assert "Total: 1" in capsys.readouterr().out
    assert list_items.call_args.kwargs["query"] == "Matrix"
    assert list_items.call_args.kwargs["limit"] is None


def test_item_search_no_cache_sets_client_flag(capsys):
    client = _client()
    with patch.object(client.items, "list_items", return_value=([], 0)):
        cmd_item(client, _args("search", "Matrix", "--no-cache"))
    assert client.no_data_cache is True
    assert "No results." in capsys.readouterr().out


def test_item_search_filters_by_type_and_year(capsys):
    client = _client()
    item = {"Id": "1", "Name": "Spider-Man", "Type": "Movie", "ProductionYear": 2026}
    with patch.object(client.items, "list_items", return_value=([item], 1)) as list_items:
        cmd_item(client, _args("search", "spider-man", "--type", "movie", "--year", "2026"))
    assert "Spider-Man" in capsys.readouterr().out
    list_items.assert_called_once_with(
        query="spider-man",
        parent_id=None,
        item_types="Movie",
        year=2026,
        limit=None,
        sort_by=None,
        desc=False,
        when_unsorted="catalog",
        use_cache=True,
    )


def test_item_search_sorts_by_size_desc(capsys):
    client = _client()
    items = [
        {"Id": "1", "Name": "Title X A", "Type": "Movie", "MediaSources": [{"Size": 1000}]},
        {"Id": "2", "Name": "Title X B", "Type": "Movie", "MediaSources": [{"Size": 3000}]},
        {"Id": "3", "Name": "Title X C", "Type": "Movie", "MediaSources": [{"Size": 2000}]},
    ]
    with patch.object(client.items, "list_items", return_value=(items, 3)):
        cmd_item(client, _args("search", "Title X", "--order-by", "size", "--desc"))
    out = capsys.readouterr().out
    assert out.index("Title X B") < out.index("Title X C") < out.index("Title X A")


def test_item_search_sorts_by_resolution_desc(capsys):
    client = _client()
    items = [
        {
            "Id": "1",
            "Name": "Title X A",
            "Type": "Movie",
            "MediaStreams": [{"Type": "Video", "Width": 1280}],
        },
        {
            "Id": "2",
            "Name": "Title X B",
            "Type": "Movie",
            "MediaStreams": [{"Type": "Video", "Width": 3840}],
        },
        {
            "Id": "3",
            "Name": "Title X C",
            "Type": "Movie",
            "MediaStreams": [{"Type": "Video", "Width": 1920}],
        },
    ]
    with patch.object(client.items, "list_items", return_value=(items, 3)):
        cmd_item(client, _args("search", "Title X", "--order-by", "resolution", "--desc"))
    out = capsys.readouterr().out
    assert out.index("Title X B") < out.index("Title X C") < out.index("Title X A")


def test_item_search_uses_disk_cache_between_calls(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = _client()
    client.use_data_cache = True
    item = {"Id": "1", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 1999}
    args = _args("search", "Matrix")
    with patch.object(client, "_paginate", return_value=([item], 1)) as paginate:
        cmd_item(client, args)
        capsys.readouterr()
        cmd_item(client, args)
        capsys.readouterr()
    assert paginate.call_count == 1


def test_item_search_no_cache_refreshes_between_calls(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = _client()
    client.use_data_cache = True
    items = [
        {"Id": "1", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 2020},
        {"Id": "2", "Name": "Matrix Reloaded", "Type": "Movie", "ProductionYear": 2021},
    ]
    args = _args("search", "Matrix", "--no-cache")
    with patch.object(
        client,
        "_paginate",
        side_effect=[([items[0]], 1), ([items[1]], 1)],
    ) as paginate:
        cmd_item(client, args)
        first = capsys.readouterr().out
        cmd_item(client, args)
        second = capsys.readouterr().out
    assert "The Matrix" in first
    assert "Matrix Reloaded" in second
    assert paginate.call_count == 2
