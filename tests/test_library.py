"""Library command behavior and observable CLI contracts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from emby_cli.cli import build_parser
from emby_cli.client import EmbyClient
from emby_cli.commands.library import cmd_library
from emby_cli.output import Stats


def _client() -> EmbyClient:
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    return client


def _args(*values: str):
    return build_parser().parse_args(["library", *values])


def test_library_search_output_and_count(capsys):
    client = _client()
    libraries = [
        {"Id": "1", "Name": "Movies", "CollectionType": "movies"},
        {"Id": "2", "Name": "Series", "CollectionType": "tvshows"},
    ]
    rows = [
        {"Id": "1", "Name": "Movies", "Type": "movies", "ItemCount": 10},
        {"Id": "2", "Name": "Series", "Type": "tvshows", "ItemCount": 20},
    ]
    with (
        patch.object(client.libraries, "search", return_value=libraries) as search,
        patch("emby_cli.commands.library.library_rows", return_value=rows),
    ):
        cmd_library(client, _args("search", "s", "--count", "1", "--order-by", "items", "--desc"))
    out = capsys.readouterr().out
    assert "Series" in out
    assert "Movies" not in out
    assert "Total: 1 (out of 2)" in out
    search.assert_called_once_with("s", use_cache=True)


def test_library_list_shows_all_without_count_cap(capsys):
    client = _client()
    libraries = [
        {"Id": "1", "Name": "Movies", "CollectionType": "movies"},
        {"Id": "2", "Name": "Series", "CollectionType": "tvshows"},
    ]
    rows = [
        {"Id": "1", "Name": "Movies", "Type": "movies", "ItemCount": 10},
        {"Id": "2", "Name": "Series", "Type": "tvshows", "ItemCount": 20},
    ]
    with (
        patch.object(client.libraries, "search", return_value=libraries) as search,
        patch("emby_cli.commands.library.library_rows", return_value=rows),
    ):
        cmd_library(client, _args("list"))
    out = capsys.readouterr().out
    assert "Movies" in out
    assert "Series" in out
    assert "Total: 2" in out
    assert "out of" not in out
    search.assert_called_once_with("", use_cache=True)


def test_library_show_prints_recent_items(capsys):
    client = _client()
    library = {"Id": "100", "Name": "Movies", "CollectionType": "movies"}
    pages = [
        {"TotalRecordCount": 42},
        {"Items": [{
            "Id": "m1",
            "Name": "New Movie",
            "Type": "Movie",
            "ProductionYear": 2024,
            "DateCreated": "2024-06-01T12:00:00.0000000Z",
        }]},
    ]
    with patch.object(client.libraries, "list", return_value=[library]), patch.object(
        client,
        "get_items",
        side_effect=pages,
    ):
        cmd_library(client, _args("show", "Movies"))
    out = capsys.readouterr().out
    assert "name: Movies" in out
    assert "items: 42" in out
    assert "Recently added" in out
    assert out.count("New Movie") == 1
    assert "2024-06-01 12:00:00" in out


def test_library_show_parent_id_before_subcommand():
    client = _client()
    library = {"Id": "100", "Name": "Movies", "CollectionType": "movies"}
    with (
        patch.object(client.libraries, "list", return_value=[library]),
        patch("emby_cli.commands.library.print_library") as print_library,
    ):
        cmd_library(client, _args("--id", "100", "show"))
    print_library.assert_called_once_with(client, library)


def test_library_show_missing_id_reports_stderr(capsys):
    client = _client()
    with patch.object(client.libraries, "list", return_value=[]), pytest.raises(SystemExit) as exc:
        cmd_library(client, _args("show", "--id", "missing"))
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "library id 'missing' not found" in captured.err
    assert captured.out == ""


def test_library_download_delegates_to_library_ops():
    client = _client()
    library = {"Id": "100", "Name": "Movies", "CollectionType": "movies"}
    with (
        patch("emby_cli.commands.library.resolve_library", return_value=library),
        patch("emby_cli.commands.library.download_library", return_value=Stats(ok=2)) as download,
        patch("emby_cli.commands.library.print_done"),
    ):
        with pytest.raises(SystemExit) as exc:
            cmd_library(client, _args("download", "Movies", "--dry-run"))
    assert exc.value.code == 0
    download.assert_called_once()


def test_library_download_ambiguous_prints_candidates(capsys):
    client = _client()
    libraries = [
        {"Id": "a", "Name": "Movies", "CollectionType": "movies"},
        {"Id": "b", "Name": "Movies 4K", "CollectionType": "movies"},
    ]
    with patch.object(client.libraries, "list", return_value=libraries), pytest.raises(
        SystemExit,
    ) as exc:
        cmd_library(client, _args("download", "Movies", "--dry-run"))
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "ambiguous" in captured.err
    assert "Movies" in captured.out
    assert "Movies 4K" in captured.out


def test_library_play_delegates_to_library_ops():
    client = _client()
    library = {"Id": "100", "Name": "Movies", "CollectionType": "movies"}
    with (
        patch("emby_cli.commands.library.resolve_library", return_value=library),
        patch("emby_cli.commands.library.find_player", return_value=["vlc"]),
        patch("emby_cli.commands.library.play_library", return_value=0) as play,
    ):
        cmd_library(client, _args("play", "Movies", "--player", "vlc"))
    play.assert_called_once()
    assert play.call_args.kwargs["wait"] is True


def test_library_search_filters_by_type(capsys):
    client = _client()
    libraries = [
        {"Id": "1", "Name": "Movies", "CollectionType": "movies"},
        {"Id": "2", "Name": "Series", "CollectionType": "tvshows"},
    ]
    rows = [{"Id": "1", "Name": "Movies", "Type": "movies", "ItemCount": 10}]
    with (
        patch.object(client.libraries, "search", return_value=libraries),
        patch("emby_cli.commands.library.library_rows", return_value=rows) as library_rows,
    ):
        cmd_library(client, _args("search", "--type", "movies", "--count", "all"))
    out = capsys.readouterr().out
    assert "Movies" in out
    assert "Series" not in out
    library_rows.assert_called_once()
    passed = library_rows.call_args.args[1]
    assert passed == [libraries[0]]


def test_library_search_count_all_is_distinct_from_list(capsys):
    client = _client()
    library = {"Id": "1", "Name": "Movies", "CollectionType": "movies"}
    row = {"Id": "1", "Name": "Movies", "Type": "movies", "ItemCount": 10}
    with patch.object(client.libraries, "search", return_value=[library]) as search, patch(
        "emby_cli.commands.library.library_rows",
        return_value=[row],
    ):
        cmd_library(client, _args("search", "Mov", "--count", "all"))
    assert "Total: 1" in capsys.readouterr().out
    search.assert_called_once_with("Mov", use_cache=True)


def test_library_search_no_cache_sets_client_flag(capsys):
    client = _client()
    with patch.object(client.libraries, "search", return_value=[]):
        cmd_library(client, _args("search", "Movies", "--no-cache"))
    assert client.no_data_cache is True
    assert "No results." in capsys.readouterr().out


def test_library_search_sorts_by_name_asc(capsys):
    client = _client()
    libraries = [
        {"Id": "2", "Name": "ZZZ", "CollectionType": "movies"},
        {"Id": "1", "Name": "AAA", "CollectionType": "movies"},
    ]
    rows = [
        {"Id": "2", "Name": "ZZZ", "Type": "movies", "ItemCount": 1},
        {"Id": "1", "Name": "AAA", "Type": "movies", "ItemCount": 2},
    ]
    with (
        patch.object(client.libraries, "search", return_value=libraries),
        patch("emby_cli.commands.library.library_rows", return_value=rows),
    ):
        cmd_library(client, _args("search", "--count", "all", "--order-by", "name"))
    out = capsys.readouterr().out
    assert out.index("AAA") < out.index("ZZZ")
