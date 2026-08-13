"""Tests for search listing and filters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from emby_cli.client import EmbyClient
from emby_cli.commands import search as search_mod


def _list_items_kwargs(**overrides):
    base = {
        "query": "",
        "parent_id": None,
        "item_types": "Movie,Episode,Audio,Video",
        "year": None,
        "limit": None,
        "sort_by": None,
        "desc": False,
        "when_unsorted": "catalog",
        "use_cache": True,
    }
    base.update(overrides)
    return base


def _search_kwargs(**overrides):
    base = {
        "item_types": "Movie,Episode,Audio,Video",
        "year": None,
        "limit": None,
        "sort_by": None,
        "desc": False,
        "use_cache": True,
    }
    base.update(overrides)
    return base


def test_item_count_all_lists_everything(capsys):
    client = MagicMock()
    client.items.list_items.return_value = (
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
    client.items.list_items.assert_called_once_with(**_list_items_kwargs())


def test_item_query_shows_out_of_when_truncated(capsys):
    client = MagicMock()
    client.items.list_items.return_value = (
        [
            {"Id": str(i), "Name": f"Matrix {i}", "Type": "Movie", "ProductionYear": 2000 + i}
            for i in range(14)
        ],
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
    client.items.list_items.assert_called_once_with(
        **_list_items_kwargs(query="matrix"),
    )


def test_item_query_plain_total_when_complete(capsys):
    client = MagicMock()
    client.items.list_items.return_value = (
        [
            {"Id": "1", "Name": "unique title", "Type": "Movie", "ProductionYear": 1999},
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
    client.items.list_items.return_value = (
        [
            {"Id": "1", "Name": "Spider-Man", "Type": "Movie", "ProductionYear": 2026},
        ],
        1,
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
    client.items.list_items.assert_called_once_with(
        **_list_items_kwargs(
            query="spider-man",
            item_types="Movie",
            year=2026,
        ),
    )


def test_item_query_filters_lowercase_type(capsys):
    client = MagicMock()
    client.items.list_items.return_value = (
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
    client.items.list_items.assert_called_once_with(
        **_list_items_kwargs(
            query="spider-man",
            item_types="Movie",
            year=2026,
        ),
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


def test_library_without_query_and_count_one_shows_top_one(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "1", "Name": "Small", "CollectionType": "movies", "Type": "CollectionFolder"},
        {"Id": "2", "Name": "Big", "CollectionType": "movies", "Type": "CollectionFolder"},
    ]
    client.get_items.side_effect = [
        {"TotalRecordCount": 2},    # Small
        {"TotalRecordCount": 100},  # Big
    ]
    args = MagicMock(
        count=1,
        id=None,
        search=None,
        item=None,
        library="",
        order_by="items",
        desc=True,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert "Big" in out
    assert "Small" not in out
    assert "Total: 1 (out of 2)" in out


def test_library_type_filter_tvshows(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "1", "Name": "Movies", "CollectionType": "movies", "Type": "CollectionFolder"},
        {"Id": "2", "Name": "Series", "CollectionType": "tvshows", "Type": "CollectionFolder"},
    ]
    args = MagicMock(
        count="all",
        id=None,
        search=None,
        item=None,
        library="",
        item_type="tvshows",
        order_by="name",
        desc=False,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert "Series" in out
    assert "Movies" not in out


def test_item_query_sorts_by_year_desc(capsys):
    client = MagicMock()
    client.items.list_items.return_value = (
        [
            {"Id": "2", "Name": "Spider-Man B", "Type": "Movie", "ProductionYear": 2026},
            {"Id": "3", "Name": "Spider-Man C", "Type": "Movie", "ProductionYear": 2024},
            {"Id": "1", "Name": "Spider-Man A", "Type": "Movie", "ProductionYear": 2021},
        ],
        3,
    )
    args = MagicMock(
        count="all",
        id=None,
        search=None,
        item="spider-man",
        library=None,
        item_type=None,
        year=None,
        order_by="year",
        desc=True,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert out.index("2026") < out.index("2024") < out.index("2021")
    client.items.list_items.assert_called_once_with(
        **_list_items_kwargs(query="spider-man", sort_by="year", desc=True),
    )


def test_library_query_sorts_by_name_asc(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "9", "Name": "Zeta", "CollectionType": "movies"},
        {"Id": "1", "Name": "Alpha", "CollectionType": "movies"},
    ]
    args = MagicMock(
        count="all",
        id=None,
        search="",
        item=None,
        library="",
        order_by="name",
        desc=False,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert out.index("Alpha") < out.index("Zeta")


def test_library_query_sorts_by_items_desc(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "1", "Name": "Small", "CollectionType": "movies", "Type": "CollectionFolder", "ItemCount": 2},
        {"Id": "2", "Name": "Big", "CollectionType": "movies", "Type": "CollectionFolder", "ItemCount": 100},
    ]
    client.get_items.side_effect = [
        {"TotalRecordCount": 2},    # Id 1
        {"TotalRecordCount": 100},  # Id 2
    ]
    args = MagicMock(
        count="all",
        id=None,
        search="",
        item=None,
        library="",
        order_by="items",
        desc=True,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert out.index("Big") < out.index("Small")


def test_library_query_sorts_by_items_desc_using_computed_counts(capsys):
    client = MagicMock()
    client.get_libraries.return_value = [
        {"Id": "1", "Name": "Movies", "CollectionType": "movies", "Type": "CollectionFolder"},
        {"Id": "2", "Name": "Series", "CollectionType": "movies", "Type": "CollectionFolder"},
    ]
    client.get_items.side_effect = [
        {"TotalRecordCount": 10},   # Id 1
        {"TotalRecordCount": 500},  # Id 2
    ]
    args = MagicMock(
        count="all",
        id=None,
        search="",
        item=None,
        library="",
        order_by="items",
        desc=True,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert out.index("Series") < out.index("Movies")


def test_item_query_sorts_by_size_desc(capsys):
    client = MagicMock()
    client.items.list_items.return_value = (
        [
            {"Id": "1", "Name": "Title X A", "Type": "Movie", "MediaSources": [{"Size": 1000}]},
            {"Id": "2", "Name": "Title X B", "Type": "Movie", "MediaSources": [{"Size": 3000}]},
            {"Id": "3", "Name": "Title X C", "Type": "Movie", "MediaSources": [{"Size": 2000}]},
        ],
        3,
    )
    args = MagicMock(
        count="all",
        id=None,
        search=None,
        item="x",
        library=None,
        order_by="size",
        desc=True,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert out.index("B") < out.index("C") < out.index("A")


def test_item_query_sorts_by_resolution_desc(capsys):
    client = MagicMock()
    client.items.list_items.return_value = (
        [
            {"Id": "1", "Name": "Title X A", "Type": "Movie", "MediaStreams": [{"Type": "Video", "Width": 1280}]},
            {"Id": "2", "Name": "Title X B", "Type": "Movie", "MediaStreams": [{"Type": "Video", "Width": 3840}]},
            {"Id": "3", "Name": "Title X C", "Type": "Movie", "MediaStreams": [{"Type": "Video", "Width": 1920}]},
        ],
        3,
    )
    args = MagicMock(
        count="all",
        id=None,
        search=None,
        item="x",
        library=None,
        order_by="resolution",
        desc=True,
    )
    search_mod.cmd_search(client, args)
    out = capsys.readouterr().out
    assert out.index("B") < out.index("C") < out.index("A")


def test_library_items_uses_disk_cache_between_calls(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = MagicMock()
    client.server_url = "http://x"
    client.resolve_user_id.return_value = "u1"
    client.get_libraries.return_value = [
        {"Id": "1", "Name": "Movies", "CollectionType": "movies", "Type": "CollectionFolder"},
    ]
    client.get_items.return_value = {"TotalRecordCount": 123}
    args = MagicMock(
        count=1,
        id=None,
        search=None,
        item=None,
        library="",
        order_by="items",
        desc=True,
        no_cache=False,
    )
    search_mod.cmd_search(client, args)
    _ = capsys.readouterr()
    search_mod.cmd_search(client, args)
    _ = capsys.readouterr()
    assert client.get_libraries.call_count == 1
    assert client.get_items.call_count == 1


def test_library_items_no_cache_refreshes_disk(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = MagicMock()
    client.server_url = "http://x"
    client.resolve_user_id.return_value = "u1"
    client.get_libraries.return_value = [
        {"Id": "1", "Name": "Movies", "CollectionType": "movies", "Type": "CollectionFolder"},
    ]
    client.get_items.side_effect = [
        {"TotalRecordCount": 10},
        {"TotalRecordCount": 20},
    ]
    args = MagicMock(
        count=1,
        id=None,
        search=None,
        item=None,
        library="",
        order_by="items",
        desc=True,
        no_cache=True,
    )
    search_mod.cmd_search(client, args)
    first = capsys.readouterr().out
    search_mod.cmd_search(client, args)
    second = capsys.readouterr().out
    assert "10" in first
    assert "20" in second
    assert client.get_libraries.call_count == 2
    assert client.get_items.call_count == 2


def test_item_query_uses_disk_cache_between_calls(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = EmbyClient("http://x", api_key="k")
    client.user_id = "u1"
    client.use_data_cache = True
    args = MagicMock(
        count="all",
        id=None,
        search=None,
        item="matrix",
        library=None,
        item_type=None,
        year=None,
        order_by=None,
        desc=False,
        no_cache=False,
    )
    with patch.object(
        client,
        "_paginate",
        return_value=([{"Id": "1", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 2020}], 1),
    ) as paginate:
        search_mod.cmd_search(client, args)
        _ = capsys.readouterr()
        search_mod.cmd_search(client, args)
        _ = capsys.readouterr()
    assert paginate.call_count == 1


def test_item_query_no_cache_refreshes_disk(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = EmbyClient("http://x", api_key="k")
    client.user_id = "u1"
    client.use_data_cache = True
    args = MagicMock(
        count="all",
        id=None,
        search=None,
        item="matrix",
        library=None,
        item_type=None,
        year=None,
        order_by=None,
        desc=False,
        no_cache=True,
    )
    with patch.object(
        client,
        "_paginate",
        side_effect=[
            ([{"Id": "1", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 2020}], 1),
            ([{"Id": "2", "Name": "Matrix Reloaded", "Type": "Movie", "ProductionYear": 2021}], 1),
        ],
    ) as paginate:
        search_mod.cmd_search(client, args)
        first = capsys.readouterr().out
        search_mod.cmd_search(client, args)
        second = capsys.readouterr().out
    assert "The Matrix" in first
    assert "Matrix Reloaded" in second
    assert paginate.call_count == 2
