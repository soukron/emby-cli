"""Item matching and resolution helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import SHOW_ITEM_FIELDS
from emby_cli.item_ops import (
    ItemListingQuery,
    ItemResolutionError,
    build_item_listing_query,
    episodes_for_title_line,
    fetch_item_listing,
    item_types_for_api,
    normalize_item_type,
    playable_items_for_parent,
    resolve_item,
    split_listing_search_query,
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


def test_build_item_listing_query_delegates_year_and_count_to_api():
    listing = build_item_listing_query(
        query="",
        raw_type="movie",
        year=2026,
        count=30,
        order_by="year",
        desc=True,
    )
    assert listing.item_types == "Movie"
    assert listing.year == 2026
    assert listing.api_limit == 30
    assert listing.order_by == "year"
    assert listing.desc is True


def test_split_listing_search_query_parses_title_year():
    assert split_listing_search_query("Matrix (1999)") == ("Matrix", 1999)
    assert split_listing_search_query("matrix", year=1999) == ("matrix", 1999)
    assert split_listing_search_query("Matrix (1999)", year=2000) == ("Matrix", 2000)


def test_build_item_listing_query_strict_by_default():
    listing = build_item_listing_query(query="Matrix (1999)", raw_type="movie")
    assert listing.query == "Matrix (1999)"
    assert listing.title_line is None
    assert listing.year is None


def test_build_item_listing_query_parses_title_line_year():
    listing = build_item_listing_query(
        query="Matrix (1999)",
        raw_type="movie",
        parse_query=True,
    )
    assert listing.query == "Matrix"
    assert listing.title_line is None
    assert listing.year == 1999


def test_build_item_listing_query_parses_series_episode_line():
    listing = build_item_listing_query(query="Californication S01E01", parse_query=True)
    assert listing.query == "Californication"
    assert listing.title_line == "Californication S01E01"
    assert listing.year is None


def test_episodes_for_title_line_resolves_series_episode():
    client = _client()
    series = {"Id": "s1", "Name": "Californication", "Type": "Series", "ProductionYear": 2007}
    episode = {
        "Id": "e1",
        "Name": "Pilot",
        "Type": "Episode",
        "ParentIndexNumber": 1,
        "IndexNumber": 1,
        "SeriesName": "Californication",
    }
    with (
        patch.object(client, "search_items", return_value=[series]) as search_items,
        patch.object(client, "get_show_episodes", return_value=[episode]) as get_eps,
    ):
        items = episodes_for_title_line(client, "Californication S01E01")
    assert items == [episode]
    search_items.assert_called_once_with("Californication", item_types="Series")
    get_eps.assert_called_once_with("s1", season=1)


def test_fetch_item_listing_uses_episode_resolver_for_title_line():
    client = _client()
    episode = {"Id": "e1", "Name": "Pilot", "Type": "Episode"}
    listing = build_item_listing_query(query="Californication S01E01", count=1, parse_query=True)
    with patch(
        "emby_cli.item_ops.episodes_for_title_line",
        return_value=[episode, {"Id": "e2", "Name": "Other", "Type": "Episode"}],
    ) as resolve:
        shown, total = fetch_item_listing(client, listing, use_cache=False)
    assert len(shown) == 1
    assert total == 2
    resolve.assert_called_once()


def test_resolve_item_by_title_line_episode():
    client = _client()
    episode = {"Id": "e1", "Name": "Pilot", "Type": "Episode"}
    with patch(
        "emby_cli.item_ops.episodes_for_title_line",
        return_value=[episode],
    ):
        assert resolve_item(
            client,
            query="Californication S01E01",
            use_cache=False,
            parse_query=True,
        ) == episode


def test_resolve_item_strict_sends_full_query():
    client = _client()
    with patch.object(client.items, "search", return_value=([ITEMS[0]], 1)) as search:
        assert resolve_item(client, query="Matrix (1999)", use_cache=False) == ITEMS[0]
    search.assert_called_once_with(
        "Matrix (1999)",
        item_types="Movie,Episode,Audio,Video",
        year=None,
        use_cache=False,
    )


def test_resolve_item_by_title_line_uses_year_filter():
    client = _client()
    with patch.object(client.items, "search", return_value=([ITEMS[0]], 1)) as search:
        assert resolve_item(
            client,
            query="Matrix (1999)",
            use_cache=False,
            parse_query=True,
        ) == ITEMS[0]
    search.assert_called_once_with(
        "Matrix",
        item_types="Movie,Episode,Audio,Video",
        year=1999,
        use_cache=False,
    )


def test_playable_items_for_parent_delegates_to_fetch_item_listing():
    client = _client()
    listing = ItemListingQuery(
        parent_id="569",
        item_types="Movie,Episode,Audio,Video",
        order_by="added",
        desc=True,
        when_unsorted="parent",
    )
    with patch(
        "emby_cli.item_ops.fetch_item_listing",
        return_value=([{"Id": "1"}], 1),
    ) as fetch:
        items = playable_items_for_parent(
            client,
            "569",
            order_by="added",
            desc=True,
            use_cache=False,
        )
    assert items == [{"Id": "1"}]
    fetch.assert_called_once()
    assert fetch.call_args.args[1] == listing
    assert fetch.call_args.kwargs["use_cache"] is False


def test_resolve_item_by_query_unique_match():
    client = _client()
    with patch.object(client.items, "search", return_value=([ITEMS[0]], 1)) as search:
        assert resolve_item(client, query="matrix", use_cache=False) == ITEMS[0]
    search.assert_called_once_with(
        "matrix",
        item_types="Movie,Episode,Audio,Video",
        year=None,
        use_cache=False,
    )


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
