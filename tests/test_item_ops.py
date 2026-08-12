"""Item matching and resolution helpers."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import SHOW_ITEM_FIELDS
from emby_cli.item_ops import (
    ItemListingQuery,
    ItemResolutionError,
    build_item_listing_query,
    emby_search_term_for_strict_query,
    episodes_for_title_line,
    fetch_item_listing,
    item_types_for_api,
    matches_strict_name_query,
    normalize_item_type,
    play_items,
    play_url,
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


def test_play_items_launches_each(capsys):
    client = MagicMock()
    items = [
        {"Id": "1", "Name": "A", "Type": "Movie", "ProductionYear": 2001},
        {"Id": "2", "Name": "B", "Type": "Episode", "ProductionYear": 2002},
    ]
    client.resolve_direct_stream_url.side_effect = ["http://u/1", "http://u/2"]
    with patch("emby_cli.item_ops.play_url", return_value=0) as launch:
        rc = play_items(client, items, ["vlc"], wait=False, show_progress=True)
    assert rc == 0
    assert launch.call_count == 2
    out = capsys.readouterr().out
    assert "[1/2] Playing: A" in out
    assert "[2/2] Playing: B" in out


def test_play_url_wait_suppresses_player_output():
    with patch("emby_cli.item_ops.subprocess.run", return_value=MagicMock(returncode=0)) as run:
        assert play_url(["vlc"], "http://u/1", wait=True) == 0
    assert run.call_args.kwargs["stdin"] is subprocess.DEVNULL
    assert run.call_args.kwargs["stdout"] is subprocess.DEVNULL
    assert run.call_args.kwargs["stderr"] is subprocess.DEVNULL


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


def test_emby_search_term_for_strict_query_prefers_text_token():
    assert emby_search_term_for_strict_query("S01E01 Piloto") == "Piloto"
    assert emby_search_term_for_strict_query("S01E01") == "S01E01"


def test_matches_strict_name_query_phrase_and_episode_code():
    pilot = {
        "Name": "Piloto",
        "Type": "Episode",
        "ParentIndexNumber": 1,
        "IndexNumber": 1,
    }
    blue_bloods = {
        "Name": "Blue Bloods (Familia de policias) - Piloto",
        "Type": "Episode",
        "ParentIndexNumber": 1,
        "IndexNumber": 1,
    }
    assert matches_strict_name_query(pilot, "S01E01 Piloto")
    assert matches_strict_name_query(pilot, "Piloto")
    assert not matches_strict_name_query(blue_bloods, "S01E01 Piloto")
    assert matches_strict_name_query(
        {"Name": "S01E01 Twirlywoos", "Type": "Episode"},
        "S01E01",
    )
    assert not matches_strict_name_query(
        {"Name": "Show - S01E01 - Episode 1", "Type": "Episode"},
        "S01E01",
    )


def test_fetch_item_listing_strict_filters_multiword_query():
    client = _client()
    candidates = [
        {
            "Id": "1",
            "Name": "Piloto",
            "Type": "Episode",
            "ParentIndexNumber": 1,
            "IndexNumber": 1,
        },
        {
            "Id": "2",
            "Name": "Blue Bloods (Familia de policias) - Piloto",
            "Type": "Episode",
            "ParentIndexNumber": 1,
            "IndexNumber": 1,
        },
    ]
    listing = build_item_listing_query(query="S01E01 Piloto", raw_type="episode")
    with patch.object(client.items, "list_items", return_value=(candidates, 2)) as list_items:
        shown, total = fetch_item_listing(client, listing, use_cache=False)
    assert shown == [candidates[0]]
    assert total == 1
    list_items.assert_called_once_with(
        query="Piloto",
        parent_id=None,
        item_types="Episode",
        year=None,
        limit=None,
        sort_by=None,
        desc=False,
        when_unsorted="catalog",
        use_cache=False,
    )


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
    with patch.object(client.items, "list_items", return_value=([ITEMS[0]], 1)) as list_items:
        assert resolve_item(client, query="Matrix", use_cache=False) == ITEMS[0]
    list_items.assert_called_once_with(
        query="Matrix",
        parent_id=None,
        item_types="Movie,Episode,Audio,Video",
        year=None,
        limit=None,
        sort_by=None,
        desc=False,
        when_unsorted="catalog",
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
        order_by="added-date",
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
            order_by="added-date",
            desc=True,
            use_cache=False,
        )
    assert items == [{"Id": "1"}]
    fetch.assert_called_once()
    assert fetch.call_args.args[1] == listing
    assert fetch.call_args.kwargs["use_cache"] is False


def test_resolve_item_by_query_unique_match():
    client = _client()
    with patch.object(client.items, "list_items", return_value=([ITEMS[0]], 1)) as list_items:
        assert resolve_item(client, query="matrix", use_cache=False) == ITEMS[0]
    list_items.assert_called_once_with(
        query="matrix",
        parent_id=None,
        item_types="Movie,Episode,Audio,Video",
        year=None,
        limit=None,
        sort_by=None,
        desc=False,
        when_unsorted="catalog",
        use_cache=False,
    )


def test_resolve_item_reports_ambiguous_candidates():
    client = _client()
    with patch.object(client.items, "list_items", return_value=(ITEMS, 2)) as list_items:
        with pytest.raises(ItemResolutionError) as exc_info:
            resolve_item(client, query="e", use_cache=False)
    assert exc_info.value.matches == ITEMS
    assert "ambiguous" in str(exc_info.value)
    list_items.assert_called_once()


def test_resolve_item_by_id_prefix_uses_catalog():
    client = _client()
    with (
        patch.object(client.items, "get", side_effect=_not_found()) as get,
        patch.object(client.items, "search", return_value=(ITEMS, 2)) as search,
    ):
        assert resolve_item(client, item_id="20", use_cache=False) == ITEMS[1]
    get.assert_called_once_with("20", fields=SHOW_ITEM_FIELDS, use_cache=False)
    search.assert_called_once_with("", item_types="Movie,Episode,Audio,Video", use_cache=False)
