"""Collection command behavior and observable CLI contracts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from emby_cli.api.collections import COLLECTION_DETAIL_FIELDS
from emby_cli.cli import build_parser, main
from emby_cli.client import EmbyClient
from emby_cli.commands.collection import cmd_collection


def _client() -> EmbyClient:
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    return client


def _args(*values: str):
    return build_parser().parse_args(["collection", *values])


def _not_found() -> requests.HTTPError:
    response = MagicMock(status_code=404)
    return requests.HTTPError("404", response=response)


def test_collection_search_output_and_count(capsys):
    client = _client()
    collections = [
        {"Id": "1", "Name": "First", "ChildCount": 2, "ProductionYear": 2000},
        {"Id": "2", "Name": "Second", "ChildCount": 4, "ProductionYear": 2010},
    ]
    with patch.object(client.collections, "search", return_value=collections) as search:
        cmd_collection(client, _args("search", "s", "--count", "1", "--order-by", "items", "--desc"))
    out = capsys.readouterr().out
    assert "Second" in out
    assert "First" not in out
    assert "Total: 1 (out of 2)" in out
    search.assert_called_once_with("s", use_cache=True)


def test_collection_list_shows_all_without_count_cap(capsys):
    client = _client()
    collections = [
        {"Id": "1", "Name": "First", "ChildCount": 2, "ProductionYear": 2000},
        {"Id": "2", "Name": "Second", "ChildCount": 4, "ProductionYear": 2010},
    ]
    with patch.object(client.collections, "search", return_value=collections) as search:
        cmd_collection(client, _args("list"))
    out = capsys.readouterr().out
    assert "First" in out
    assert "Second" in out
    assert "Total: 2" in out
    assert "out of" not in out
    search.assert_called_once_with("", use_cache=True)


def test_collection_show_lists_generic_existing_members(capsys):
    client = _client()
    collection = {"Id": "10", "Name": "Mixed", "Type": "BoxSet"}
    detail = {
        **collection,
        "SortName": "Mixed 01",
        "DisplayOrder": "SortName",
        "Overview": "A mixed collection.",
    }
    members = [
        {"Id": "20", "Name": "A Movie", "Type": "Movie", "ProductionYear": 2000},
        {"Id": "21", "Name": "A Song", "Type": "Audio"},
    ]
    with (
        patch.object(client.collections, "list", return_value=[collection]),
        patch.object(client.items, "get", return_value=detail) as get,
        patch.object(client.items, "list_all", return_value=members),
    ):
        cmd_collection(client, _args("show", "Mixed"))
    out = capsys.readouterr().out
    assert "Collection" in out
    assert "short name: Mixed 01" in out
    assert "A Movie" in out
    assert "A Song" in out
    assert "Audio" in out
    get.assert_called_once_with("10", fields=COLLECTION_DETAIL_FIELDS, use_cache=True)


def test_collection_show_no_cache_refreshes_service_cache():
    client = _client()
    collection = {"Id": "10", "Name": "Mixed", "Type": "BoxSet"}
    with (
        patch.object(client.collections, "list", return_value=[collection]) as listing,
        patch.object(client.items, "get", return_value=collection) as get,
        patch.object(client.items, "list_all", return_value=[]),
    ):
        cmd_collection(client, _args("show", "Mixed", "--no-cache"))
    assert client.no_data_cache is True
    listing.assert_called_once_with(use_cache=True)
    get.assert_called_once_with("10", fields=COLLECTION_DETAIL_FIELDS, use_cache=True)


def test_collection_create_with_no_members(capsys):
    client = _client()
    with patch.object(
        client.collections,
        "create",
        return_value={"Id": "10", "Name": "Saga"},
    ) as create:
        cmd_collection(client, _args("create", "Saga"))
    assert "Created collection [10] Saga" in capsys.readouterr().out
    create.assert_called_once_with("Saga", item_ids=[])


def test_add_items_partial_success_reports_error_and_continues(capsys):
    client = _client()
    collection = {"Id": "10", "Name": "Saga", "Type": "BoxSet"}
    movie = {"Id": "1", "Name": "Movie", "Type": "Movie"}
    audio = {"Id": "2", "Name": "Song", "Type": "Audio"}
    with (
        patch.object(client.collections, "list", return_value=[collection]),
        patch.object(client.items, "get", side_effect=[movie, audio, _not_found()]),
        patch.object(client.items, "list_all", return_value=[]),
        patch.object(client.collections, "add_items") as add,
    ):
        with pytest.raises(SystemExit) as exc_info:
            cmd_collection(
                client,
                _args("add-item", "--id", "10", "--item", "1,2,missing"),
            )
    assert exc_info.value.code == 1
    add.assert_called_once_with("10", ["1"])
    captured = capsys.readouterr()
    assert "Done. ok=1 skip=0 error=2" in captured.out
    assert "has type Audio" in captured.err
    assert "not found" in captured.err


def test_remove_items_all_valid(capsys):
    client = _client()
    collection = {"Id": "10", "Name": "Saga", "Type": "BoxSet"}
    with (
        patch.object(client.collections, "list", return_value=[collection]),
        patch.object(
            client.items,
            "get",
            side_effect=[
                {"Id": "1", "Type": "Movie"},
                {"Id": "2", "Type": "Movie"},
            ],
        ),
        patch.object(client.collections, "remove_items") as remove,
    ):
        cmd_collection(client, _args("remove-item", "Saga", "--item", "1,2"))
    remove.assert_called_once_with("10", ["1", "2"])
    assert "Done. ok=2 skip=0 error=0" in capsys.readouterr().out


def test_rename_preserves_short_name_when_flag_omitted(capsys):
    client = _client()
    collection = {"Id": "10", "Name": "Old", "Type": "BoxSet"}
    detail = {**collection, "SortName": "Custom order"}
    with (
        patch.object(client.collections, "list", return_value=[collection]),
        patch.object(client.items, "get", return_value=detail),
        patch.object(client.items, "update") as update,
        patch.object(client.collections, "invalidate"),
    ):
        cmd_collection(client, _args("rename", "Old", "New"))
    payload = update.call_args.args[1]
    assert payload["Name"] == "New"
    assert payload["SortName"] == "Custom order"
    assert "Renamed collection [10] to New" in capsys.readouterr().out


def test_rename_updates_short_name_when_requested():
    client = _client()
    collection = {"Id": "10", "Name": "Old", "Type": "BoxSet"}
    with (
        patch.object(client.collections, "list", return_value=[collection]),
        patch.object(client.items, "get", return_value=dict(collection)),
        patch.object(client.items, "update") as update,
        patch.object(client.collections, "invalidate"),
    ):
        cmd_collection(
            client,
            _args("rename", "--id", "10", "New", "--short-name", "New 01"),
        )
    payload = update.call_args.args[1]
    assert payload["Name"] == "New"
    assert payload["SortName"] == "New 01"


def test_delete_yes_skips_prompt(capsys):
    client = _client()
    collection = {"Id": "10", "Name": "Saga", "Type": "BoxSet"}
    with (
        patch.object(client.collections, "list", return_value=[collection]),
        patch.object(client.items, "get", return_value=collection),
        patch("builtins.input") as prompt,
        patch.object(client.collections, "delete") as delete,
    ):
        cmd_collection(client, _args("delete", "--id", "10", "--yes"))
    prompt.assert_not_called()
    delete.assert_called_once_with("10")
    assert "member media was not deleted" in capsys.readouterr().out


def test_delete_interactive_no_cancels(capsys):
    client = _client()
    collection = {"Id": "10", "Name": "Saga", "Type": "BoxSet"}
    with (
        patch.object(client.collections, "list", return_value=[collection]),
        patch.object(client.items, "get", return_value=collection),
        patch("sys.stdin.isatty", return_value=True),
        patch("builtins.input", return_value="no"),
        patch.object(client.collections, "delete") as delete,
    ):
        cmd_collection(client, _args("delete", "Saga"))
    delete.assert_not_called()
    assert "Cancelled." in capsys.readouterr().out


def test_delete_noninteractive_requires_yes(capsys):
    client = _client()
    collection = {"Id": "10", "Name": "Saga", "Type": "BoxSet"}
    with (
        patch.object(client.collections, "list", return_value=[collection]),
        patch.object(client.items, "get", return_value=collection),
        patch("sys.stdin.isatty", return_value=False),
        patch.object(client.collections, "delete") as delete,
    ):
        with pytest.raises(SystemExit) as exc_info:
            cmd_collection(client, _args("delete", "Saga"))
    assert exc_info.value.code == 1
    delete.assert_not_called()
    assert "pass --yes" in capsys.readouterr().err


def test_collection_set_with_parent_id(capsys):
    client = _client()
    collection = {"Id": "1234", "Name": "Old", "Type": "BoxSet"}
    with (
        patch.object(client.collections, "list", return_value=[collection]),
        patch.object(
            client.items,
            "get",
            return_value={"Id": "1234", "Name": "Old", "Type": "BoxSet", "SortName": "Old"},
        ),
        patch.object(client.items, "merge_and_update") as merge,
        patch.object(client.collections, "invalidate") as invalidate,
    ):
        cmd_collection(
            client,
            _args("--id", "1234", "set", "year=1980", "name=Peliculas"),
        )
    merge.assert_called_once_with(
        "1234",
        {
            "ProductionYear": 1980,
            "Name": "Peliculas",
        },
    )
    invalidate.assert_called_once_with("1234")
    out = capsys.readouterr().out
    assert "Updated collection [1234]" in out
    assert "year=1980" in out
    assert "name='Peliculas'" in out


def test_main_collection_403_has_permission_message(capsys, monkeypatch):
    client = _client()
    response = MagicMock(status_code=403)
    error = requests.HTTPError("403", response=response)
    monkeypatch.setattr(
        "sys.argv",
        ["emby-cli", "--server", "http://host:8096", "collection", "search"],
    )
    with (
        patch("emby_cli.cli._open_client", return_value=client),
        patch.object(client.collections, "search", side_effect=error),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1
    assert "requires metadata edit permissions" in capsys.readouterr().err
