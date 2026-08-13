"""HTTP contracts for media item search on ItemsService."""

from __future__ import annotations

from unittest.mock import patch

from emby_cli.client import EmbyClient
from emby_cli.constants import SEARCH_ITEM_TYPES
from emby_cli.data_cache import load_json, save_json


def _client() -> EmbyClient:
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    return client


def test_items_search_uses_search_term_and_v2_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = _client()
    client.use_data_cache = True
    with patch.object(client, "_paginate", return_value=([{"Id": "1", "Name": "Movie"}], 1)) as paginate:
        items, total = client.items.search("star", use_cache=True)
    assert items == [{"Id": "1", "Name": "Movie"}]
    assert total == 1
    paginate.assert_called_once()
    params = paginate.call_args.args[1]
    assert params["SearchTerm"] == "star"
    assert params["IncludeItemTypes"] == SEARCH_ITEM_TYPES
    assert params["SortBy"] == "DateCreated"
    assert params["SortOrder"] == "Descending"
    assert "Years" not in params
    assert paginate.call_args.kwargs["limit"] is None

    client.no_data_cache = False
    items2, total2 = client.items.search("star", use_cache=True)
    assert items2 == items
    assert total2 == total
    assert paginate.call_count == 1


def test_items_search_passes_year_and_limit_to_emby():
    client = _client()
    with patch.object(client, "_paginate", return_value=([], 0)) as paginate:
        client.items.search(
            "",
            item_types="Movie",
            year=2026,
            limit=30,
            sort_by="year",
            desc=True,
            use_cache=False,
        )
    params = paginate.call_args.args[1]
    assert params["Years"] == "2026"
    assert params["IncludeItemTypes"] == "Movie"
    assert params["SortBy"] == "ProductionYear"
    assert params["SortOrder"] == "Descending"
    assert paginate.call_args.kwargs["limit"] == 30


def test_items_search_no_cache_bypasses_read_and_refreshes_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = _client()
    client.use_data_cache = True
    key = client.items._search_key("", SEARCH_ITEM_TYPES)
    save_json(key, {"items": [{"Id": "old"}], "total": 1})
    client.no_data_cache = True
    with patch.object(
        client,
        "_paginate",
        return_value=([{"Id": "fresh"}], 1),
    ) as paginate:
        items, total = client.items.search("", use_cache=True)
    assert items == [{"Id": "fresh"}]
    assert total == 1
    paginate.assert_called_once()
    client.no_data_cache = False
    assert load_json(key) == {"items": [{"Id": "fresh"}], "total": 1}
