"""Tests for EmbyClient helpers (no live server)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from emby_cli.client import EmbyClient
from emby_cli.constants import CLIENT_NAME, DOWNLOADABLE_TYPES, SEARCH_ITEM_TYPES


def test_session_user_agent_identifies_client():
    client = EmbyClient("http://host:8096", api_key="k")
    ua = client.session.headers.get("User-Agent")
    assert ua is not None
    assert ua.startswith(f"{CLIENT_NAME}/")
    assert not ua.startswith("python-requests")


def test_search_item_types_matches_downloadable_types():
    assert SEARCH_ITEM_TYPES == ",".join(DOWNLOADABLE_TYPES)


def test_server_url_strips_emby_suffix():
    c = EmbyClient("http://host:8096/emby", api_key="k")
    assert c.server_url == "http://host:8096"
    assert c._url("/Users/Me") == "http://host:8096/emby/Users/Me"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("Videos/1/original.mp4", "http://host:8096/emby/Videos/1/original.mp4"),
        ("/emby/Videos/1/original.mp4", "http://host:8096/emby/Videos/1/original.mp4"),
        ("https://cdn.example/original.mp4", "https://cdn.example/original.mp4"),
    ],
)
def test_url_normalizes_direct_stream_path(path, expected):
    assert EmbyClient("http://host:8096")._url(path) == expected


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


def test_get_all_items_uses_common_pagination():
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    page1 = MagicMock()
    page1.json.return_value = {"Items": [{"Id": "1"}], "TotalRecordCount": 2}
    page2 = MagicMock()
    page2.json.return_value = {"Items": [{"Id": "2"}], "TotalRecordCount": 2}

    with patch.object(client, "_get", side_effect=[page1, page2]) as get:
        assert client.get_all_items(parent_id="library") == [{"Id": "1"}, {"Id": "2"}]

    assert get.call_args_list[0].kwargs["params"]["ParentId"] == "library"
    assert get.call_args_list[1].kwargs["params"]["StartIndex"] == 1


def test_get_show_episodes_uses_common_pagination():
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    page = MagicMock()
    page.json.return_value = {"Items": [{"Id": "episode"}], "TotalRecordCount": 1}

    with patch.object(client, "_get", return_value=page) as get:
        assert client.get_show_episodes("series", season=2) == [{"Id": "episode"}]

    params = get.call_args.kwargs["params"]
    assert params["UserId"] == "uid"
    assert params["Season"] == 2


def test_download_segment_retries_when_stream_body_disconnects(tmp_path):
    client = EmbyClient("http://host:8096", api_key="k")

    def interrupted_body():
        yield b"partial-"
        raise requests.ConnectionError("disconnected")

    interrupted = MagicMock()
    interrupted.raise_for_status.return_value = None
    interrupted.iter_content.return_value = interrupted_body()
    complete = MagicMock()
    complete.raise_for_status.return_value = None
    complete.iter_content.return_value = [b"complete-segment"]
    dest = tmp_path / "segment.ts"

    with (
        patch.object(client.session, "get", side_effect=[interrupted, complete]) as get,
        patch("emby_cli.client.time.sleep"),
    ):
        client._download_segment("http://host/segment.ts", dest)

    assert get.call_count == 2
    assert dest.read_bytes() == b"complete-segment"


def test_request_retries_server_error_with_backoff():
    client = EmbyClient("http://host:8096", api_key="k")
    unavailable = MagicMock(status_code=503)
    unavailable.raise_for_status.side_effect = requests.HTTPError(
        response=unavailable
    )
    ok = MagicMock(status_code=200)
    ok.raise_for_status.return_value = None

    with (
        patch.object(client.session, "request", side_effect=[unavailable, ok]) as request,
        patch("emby_cli.client.time.sleep") as sleep,
    ):
        assert client._get("/System/Info", retries=2) is ok

    assert request.call_count == 2
    sleep.assert_called_once_with(30)


def test_download_416_promotes_complete_partial_file(tmp_path):
    client = EmbyClient("http://host:8096", api_key="k")
    dest = tmp_path / "movie.mkv"
    partial = tmp_path / "movie.mkv.part"
    partial.write_bytes(b"complete")
    response = MagicMock(status_code=416)

    with patch.object(client.session, "get", return_value=response) as get:
        result = client._download_from_url(
            "http://host/movie.mkv",
            dest,
            expected_size=len(b"complete"),
        )

    assert result == dest
    assert dest.read_bytes() == b"complete"
    assert not partial.exists()
    assert get.call_count == 1


def test_download_416_restarts_without_range_header(tmp_path):
    client = EmbyClient("http://host:8096", api_key="k")
    dest = tmp_path / "movie.mkv"
    partial = tmp_path / "movie.mkv.part"
    partial.write_bytes(b"stale")
    rejected = MagicMock(status_code=416)
    fresh = MagicMock(status_code=200)
    fresh.raise_for_status.return_value = None
    fresh.headers = {}
    fresh.iter_content.return_value = [b"fresh"]

    with patch.object(client.session, "get", side_effect=[rejected, fresh]) as get:
        result = client._download_from_url(
            "http://host/movie.mkv",
            dest,
            expected_size=10,
        )

    assert result == dest
    assert dest.read_bytes() == b"fresh"
    assert "Range" in get.call_args_list[0].kwargs["headers"]
    assert "Range" not in get.call_args_list[1].kwargs["headers"]
