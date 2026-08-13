"""HTTP contracts for the composed libraries service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from emby_cli.api.libraries import LibrariesService
from emby_cli.client import EmbyClient
from emby_cli.data_cache import load_json, save_json


def _client() -> EmbyClient:
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    return client


def test_client_exposes_libraries_service():
    client = _client()
    assert isinstance(client.libraries, LibrariesService)
    assert client.libraries.client is client


def test_libraries_list_uses_views_endpoint():
    client = _client()
    response = MagicMock()
    response.json.return_value = {"Items": [{"Id": "1", "Name": "Movies"}]}
    with patch.object(client, "_get", return_value=response) as get:
        assert client.libraries.list(use_cache=False) == [{"Id": "1", "Name": "Movies"}]
    get.assert_called_once_with("/Users/uid/Views")


def test_libraries_search_is_local_case_insensitive():
    client = _client()
    with patch.object(
        client.libraries,
        "list",
        return_value=[
            {"Id": "1", "Name": "Películas"},
            {"Id": "2", "Name": "Series"},
        ],
    ):
        assert client.libraries.search("PEL") == [{"Id": "1", "Name": "Películas"}]


def test_libraries_no_cache_bypasses_read_and_refreshes_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = _client()
    client.use_data_cache = True
    key = client.libraries._catalog_key()
    save_json(key, [{"Id": "old"}])
    client.no_data_cache = True
    response = MagicMock()
    response.json.return_value = {"Items": [{"Id": "fresh"}]}
    with patch.object(client, "_get", return_value=response) as get:
        assert client.libraries.list() == [{"Id": "fresh"}]
    get.assert_called_once()
    client.no_data_cache = False
    assert load_json(key) == [{"Id": "fresh"}]
