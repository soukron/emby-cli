"""Item matching and resolution helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import SHOW_ITEM_FIELDS
from emby_cli.item_ops import (
    ItemResolutionError,
    filter_items,
    item_types_for_api,
    normalize_item_type,
    resolve_item,
)

ITEMS = [
    {"Id": "100", "Name": "The Matrix", "Type": "Movie", "ProductionYear": 1999},
    {"Id": "200", "Name": "Inception", "Type": "Movie", "ProductionYear": 2010},
]


def _client() -> EmbyClient:
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    return client


def _not_found() -> requests.HTTPError:
    response = MagicMock(status_code=404)
    return requests.HTTPError("404", response=response)


def test_normalize_item_type_aliases():
    assert normalize_item_type("movie") == "Movie"
    assert normalize_item_type("music") == "Audio"
    assert normalize_item_type("bad") is None


def test_item_types_for_api_defaults_to_search_types():
    assert item_types_for_api(None) == "Movie,Episode,Audio,Video"
    assert item_types_for_api("episode") == "Episode"


def test_filter_items_by_type_and_year():
    filtered = filter_items(ITEMS, raw_type="movie", year=1999)
    assert filtered == [ITEMS[0]]


def test_resolve_item_by_query_unique_match():
    client = _client()
    with patch.object(client.items, "search", return_value=([ITEMS[0]], 1)) as search:
        assert resolve_item(client, query="matrix", use_cache=False) == ITEMS[0]
    search.assert_called_once_with("matrix", item_types="Movie,Episode,Audio,Video", use_cache=False)


def test_resolve_item_reports_ambiguous_candidates():
    client = _client()
    with patch.object(client.items, "search", return_value=(ITEMS, 2)) as search:
        with pytest.raises(ItemResolutionError) as exc_info:
            resolve_item(client, query="e", use_cache=False)
    assert exc_info.value.matches == ITEMS
    assert "ambiguous" in str(exc_info.value)
    search.assert_called_once()


def test_resolve_item_by_id_prefix_uses_catalog():
    client = _client()
    with (
        patch.object(client.items, "get", side_effect=_not_found()) as get,
        patch.object(client.items, "search", return_value=(ITEMS, 2)) as search,
    ):
        assert resolve_item(client, item_id="20", use_cache=False) == ITEMS[1]
    get.assert_called_once_with("20", fields=SHOW_ITEM_FIELDS, use_cache=False)
    search.assert_called_once_with("", item_types="Movie,Episode,Audio,Video", use_cache=False)
