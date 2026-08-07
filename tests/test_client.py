"""Tests for EmbyClient helpers (no live server)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from emby_cli.client import EmbyClient
from emby_cli.constants import CLIENT_NAME


def test_session_user_agent_identifies_client():
    client = EmbyClient("http://host:8096", api_key="k")
    ua = client.session.headers.get("User-Agent")
    assert ua is not None
    assert ua.startswith(f"{CLIENT_NAME}/")
    assert not ua.startswith("python-requests")


def test_server_url_strips_emby_suffix():
    c = EmbyClient("http://host:8096/emby", api_key="k")
    assert c.server_url == "http://host:8096"
    assert c._url("/Users/Me") == "http://host:8096/emby/Users/Me"


def test_ensure_api_key_appends_when_missing():
    url = EmbyClient._ensure_api_key(
        "http://host/emby/Videos/1/original.mkv?DeviceId=x",
        "tok",
    )
    assert "api_key=tok" in url


def test_ensure_api_key_noop_when_present():
    url = EmbyClient._ensure_api_key(
        "http://host/emby/Videos/1/original.mkv?api_key=old",
        "tok",
    )
    assert "api_key=old" in url
    assert "api_key=tok" not in url


def test_get_items_sort_params():
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Items": [], "TotalRecordCount": 0}
    with patch.object(client, "_get", return_value=mock_resp) as get:
        client.get_items(
            parent_id="lib",
            limit=10,
            sort_by="DateCreated",
            sort_order="Descending",
        )
    params = get.call_args.kwargs["params"]
    assert params["SortBy"] == "DateCreated"
    assert params["SortOrder"] == "Descending"
    assert params["ParentId"] == "lib"
    assert params["Limit"] == 10


def test_resolve_user_id_uses_users_me():
    client = EmbyClient("http://host:8096", api_key="k")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Id": "me-id"}
    with patch.object(client, "_get", return_value=mock_resp) as get:
        assert client.resolve_user_id() == "me-id"
    assert get.call_args.args[0] == "/Users/Me"


def test_authenticate_missing_fields():
    client = EmbyClient("http://host:8096")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    with patch.object(client, "_post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="AccessToken"):
            client.authenticate("u", "p")


def test_search_items_paginates_until_total():
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"

    page1 = MagicMock()
    page1.json.return_value = {
        "Items": [{"Id": str(i)} for i in range(200)],
        "TotalRecordCount": 250,
    }
    page2 = MagicMock()
    page2.json.return_value = {
        "Items": [{"Id": str(i)} for i in range(200, 250)],
        "TotalRecordCount": 250,
    }
    with patch.object(client, "_get", side_effect=[page1, page2]) as get:
        items = client.search_items("foo", limit=None)

    assert len(items) == 250
    assert get.call_count == 2
    assert get.call_args_list[0].kwargs["params"]["StartIndex"] == 0
    assert get.call_args_list[1].kwargs["params"]["StartIndex"] == 200


def test_search_items_respects_limit():
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    page = MagicMock()
    page.json.return_value = {
        "Items": [{"Id": str(i)} for i in range(10)],
        "TotalRecordCount": 100,
    }
    with patch.object(client, "_get", return_value=page) as get:
        items, total = client.search_items_result("foo", limit=10)

    assert len(items) == 10
    assert total == 100
    assert get.call_count == 1
    assert get.call_args.kwargs["params"]["Limit"] == 10
