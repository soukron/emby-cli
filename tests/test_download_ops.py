"""Tests for find_library / match_libraries / library_rows helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from emby_cli.constants import SHOW_LIBRARY_ITEM_TYPES
from emby_cli.download_ops import find_library, library_rows, match_libraries


LIBS = [
    {"Id": "aaaaaaaa-1111", "Name": "Movies", "CollectionType": "movies"},
    {"Id": "bbbbbbbb-2222", "Name": "TV", "CollectionType": "tvshows"},
    {"Id": "cccccccc-3333", "Name": "Movies", "CollectionType": "movies"},  # duplicate name
    {"Id": "dddddddd-4444", "Name": "Movies 4K", "CollectionType": "movies"},
]


def test_find_library_by_exact_id():
    assert find_library(LIBS[:2], library_id="aaaaaaaa-1111")["Name"] == "Movies"


def test_find_library_by_unique_prefix():
    assert find_library(LIBS[:2], library_id="bbbb")["Name"] == "TV"


def test_find_library_by_name():
    assert find_library(LIBS[:2], name="movies")["Id"] == "aaaaaaaa-1111"


def test_find_library_ambiguous_name():
    assert find_library(LIBS, name="Movies") is None


def test_find_library_missing():
    assert find_library(LIBS[:2], name="Anime") is None
    assert find_library(LIBS[:2], library_id="zzzz") is None


def test_match_libraries_substring_unique():
    matches = match_libraries(LIBS[:3], "tv")
    assert len(matches) == 1
    assert matches[0]["Id"] == "bbbbbbbb-2222"


def test_match_libraries_substring_ambiguous():
    matches = match_libraries(LIBS, "movies")
    assert len(matches) == 3
    assert {m["Id"] for m in matches} == {
        "aaaaaaaa-1111",
        "cccccccc-3333",
        "dddddddd-4444",
    }


def test_match_libraries_substring_case_insensitive():
    matches = match_libraries(LIBS[:2], "MOV")
    assert len(matches) == 1
    assert matches[0]["Name"] == "Movies"


def test_match_libraries_missing():
    assert match_libraries(LIBS, "anime") == []


def test_library_rows_filters_item_types():
    client = MagicMock()
    client.get_items.side_effect = [
        {"TotalRecordCount": 10},
        {"TotalRecordCount": 20},
    ]
    rows = library_rows(client, LIBS[:2])
    assert rows == [
        {
            "Id": "aaaaaaaa-1111",
            "Name": "Movies",
            "Type": "movies",
            "ItemCount": 10,
        },
        {
            "Id": "bbbbbbbb-2222",
            "Name": "TV",
            "Type": "tvshows",
            "ItemCount": 20,
        },
    ]
    for call in client.get_items.call_args_list:
        assert call.kwargs["item_type"] == SHOW_LIBRARY_ITEM_TYPES
        assert call.kwargs["limit"] == 0
        assert "parent_id" in call.kwargs
