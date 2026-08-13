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


def test_library_show_delegates_to_print_library():
    client = _client()
    library = {"Id": "100", "Name": "Movies", "CollectionType": "movies"}
    with (
        patch.object(client.libraries, "list", return_value=[library]),
        patch("emby_cli.commands.library._print_library") as print_library,
    ):
        cmd_library(client, _args("show", "Movies"))
    print_library.assert_called_once_with(client, library)


def test_library_show_parent_id_before_subcommand():
    client = _client()
    library = {"Id": "100", "Name": "Movies", "CollectionType": "movies"}
    with (
        patch.object(client.libraries, "list", return_value=[library]),
        patch("emby_cli.commands.library._print_library") as print_library,
    ):
        cmd_library(client, _args("--id", "100", "show"))
    print_library.assert_called_once_with(client, library)


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
