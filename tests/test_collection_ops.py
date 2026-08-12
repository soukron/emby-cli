"""Collection matching, CSV parsing, and member resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from emby_cli.client import EmbyClient
from emby_cli.collection_ops import (
    CollectionResolutionError,
    find_collection,
    match_collections,
    parse_item_refs,
    resolve_collection,
    resolve_collection_members,
)

COLLECTIONS = [
    {"Id": "1234", "Name": "Star Wars", "Type": "BoxSet"},
    {"Id": "1235", "Name": "Star Trek", "Type": "BoxSet"},
    {"Id": "9999", "Name": "Alien", "Type": "BoxSet"},
]


def _client() -> EmbyClient:
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    return client


def _not_found() -> requests.HTTPError:
    response = MagicMock(status_code=404)
    return requests.HTTPError("404", response=response)


def test_match_collections_substring_case_insensitive():
    assert match_collections(COLLECTIONS, "STAR") == COLLECTIONS[:2]


def test_find_collection_exact_and_unique_prefix():
    assert find_collection(COLLECTIONS, collection_id="1234") == COLLECTIONS[0]
    assert find_collection(COLLECTIONS, collection_id="999") == COLLECTIONS[2]
    assert find_collection(COLLECTIONS, collection_id="123") is None


def test_find_collection_exact_name_requires_unique():
    assert find_collection(COLLECTIONS, name="ALIEN") == COLLECTIONS[2]
    assert find_collection(COLLECTIONS, name="Star") is None


def test_resolve_collection_reports_ambiguous_candidates():
    client = _client()
    with patch.object(client.collections, "list", return_value=COLLECTIONS) as listing:
        with pytest.raises(CollectionResolutionError) as exc_info:
            resolve_collection(client, query="star", use_cache=False)
    assert exc_info.value.matches == COLLECTIONS[:2]
    assert "ambiguous" in str(exc_info.value)
    listing.assert_called_once_with(use_cache=False)


def test_parse_item_refs_flattens_csv_and_deduplicates_case_insensitive():
    assert parse_item_refs([" 456, 789 ", "456", "ABC,abc"]) == [
        "456", "789", "ABC",
    ]


@pytest.mark.parametrize("values", [[""], ["1,,2"], ["1,   ,2"]])
def test_parse_item_refs_rejects_empty_ids(values):
    with pytest.raises(ValueError, match="empty ID"):
        parse_item_refs(values)


def test_resolve_members_keeps_movies_and_reports_other_types():
    client = _client()
    with patch.object(
        client.items,
        "get",
        side_effect=[
            {"Id": "1", "Name": "Movie", "Type": "Movie"},
            {"Id": "2", "Name": "Song", "Type": "Audio"},
        ],
    ):
        result = resolve_collection_members(client, ["1", "2"])
    assert [item["Id"] for item in result.items] == ["1"]
    assert result.errors == [
        "item '2' has type Audio; allowed collection types: Movie",
    ]


def test_resolve_members_uses_unique_prefix_after_exact_404():
    client = _client()
    movie = {"Id": "abcdef", "Name": "Movie", "Type": "Movie"}
    with (
        patch.object(client.items, "get", side_effect=_not_found()),
        patch.object(client.items, "list_all", return_value=[movie]) as list_all,
    ):
        result = resolve_collection_members(client, ["abc"])
    assert result.items == [movie]
    assert result.errors == []
    list_all.assert_called_once_with(item_types="Movie", use_cache=False)


def test_resolve_members_reports_missing_and_continues():
    client = _client()
    movie = {"Id": "2", "Name": "Movie", "Type": "Movie"}
    with (
        patch.object(client.items, "get", side_effect=[_not_found(), movie]),
        patch.object(client.items, "list_all", return_value=[]),
    ):
        result = resolve_collection_members(client, ["missing", "2"])
    assert result.items == [movie]
    assert result.errors == ["item 'missing' not found"]
