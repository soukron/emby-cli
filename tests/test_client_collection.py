"""HTTP contracts for the composed item and collection services."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from emby_cli.api.collections import (
    COLLECTION_DETAIL_FIELDS,
    COLLECTION_FIELDS,
    CollectionsService,
)
from emby_cli.api.items import ItemsService
from emby_cli.api.libraries import LibrariesService
from emby_cli.client import EmbyClient
from emby_cli.data_cache import load_json, save_json


def _client() -> EmbyClient:
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    return client


def test_client_exposes_services_sharing_transport():
    client = _client()
    assert isinstance(client.items, ItemsService)
    assert isinstance(client.collections, CollectionsService)
    assert isinstance(client.libraries, LibrariesService)
    assert client.items.client is client
    assert client.collections.client is client


def test_items_list_all_paginates():
    client = _client()
    first = MagicMock()
    first.json.return_value = {
        "Items": [{"Id": str(i)} for i in range(200)],
        "TotalRecordCount": 201,
    }
    second = MagicMock()
    second.json.return_value = {
        "Items": [{"Id": "200"}],
        "TotalRecordCount": 201,
    }

    with patch.object(client, "_get", side_effect=[first, second]) as get:
        items = client.items.list_all(item_types="BoxSet", use_cache=False)

    assert len(items) == 201
    assert get.call_count == 2
    assert get.call_args_list[0].kwargs["params"]["IncludeItemTypes"] == "BoxSet"
    assert get.call_args_list[1].kwargs["params"]["StartIndex"] == 200


def test_items_get_without_fields_requests_complete_object():
    client = _client()
    response = MagicMock()
    response.json.return_value = {
        "Id": "1",
        "Type": "BoxSet",
        "Genres": ["Sci-Fi"],
    }
    with patch.object(client, "_get", return_value=response) as get:
        item = client.items.get("1", use_cache=False)
    assert item["Genres"] == ["Sci-Fi"]
    get.assert_called_once_with("/Users/uid/Items/1", params=None)


def test_collections_list_uses_boxset_fields():
    client = _client()
    with patch.object(client.items, "list_all", return_value=[{"Id": "1"}]) as list_all:
        assert client.collections.list(use_cache=False) == [{"Id": "1"}]
    list_all.assert_called_once_with(
        item_types="BoxSet",
        fields=COLLECTION_FIELDS,
        use_cache=False,
    )


def test_collection_search_is_local_case_insensitive():
    client = _client()
    with patch.object(
        client.collections,
        "list",
        return_value=[
            {"Id": "1", "Name": "Star Wars"},
            {"Id": "2", "Name": "Alien"},
        ],
    ):
        assert client.collections.search("WAR") == [{"Id": "1", "Name": "Star Wars"}]


def test_collections_no_cache_bypasses_read_and_refreshes_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = _client()
    client.use_data_cache = True
    key = client.collections._catalog_key()
    save_json(key, [{"Id": "old"}])
    client.no_data_cache = True
    with patch.object(client.items, "list_all", return_value=[{"Id": "fresh"}]) as listing:
        assert client.collections.list() == [{"Id": "fresh"}]
    listing.assert_called_once()
    client.no_data_cache = False
    assert load_json(key) == [{"Id": "fresh"}]


def test_create_collection_uses_query_params_no_body_and_one_attempt():
    client = _client()
    response = MagicMock()
    response.json.return_value = {"Id": "10", "Name": "Saga"}
    with (
        patch.object(client, "_post", return_value=response) as post,
        patch.object(client.collections, "invalidate_catalog") as invalidate,
    ):
        result = client.collections.create(
            "Saga",
            item_ids=["1", "2"],
            parent_id="root",
            is_locked=True,
        )

    assert result == {"Id": "10", "Name": "Saga"}
    post.assert_called_once_with(
        "/Collections",
        params={
            "Name": "Saga",
            "IsLocked": "true",
            "Ids": "1,2",
            "ParentId": "root",
        },
        retries=1,
    )
    assert post.call_args.args == ("/Collections",)
    invalidate.assert_called_once_with()


def test_add_and_remove_collection_items_use_csv_params():
    client = _client()
    with (
        patch.object(client, "_post") as post,
        patch.object(client, "_delete") as delete,
        patch.object(client.collections, "invalidate") as invalidate,
    ):
        client.collections.add_items("box", ["1", "2"])
        client.collections.remove_items("box", ["3", "4"])

    post.assert_called_once_with(
        "/Collections/box/Items",
        params={"Ids": "1,2"},
    )
    delete.assert_called_once_with(
        "/Collections/box/Items",
        params={"Ids": "3,4"},
    )
    assert invalidate.call_args_list == [call("box"), call("box")]


def test_collection_mutation_invalidates_catalog_detail_and_members(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = _client()
    catalog_key = client.collections._catalog_key()
    item_key = client.items._key("box", None)
    detail_key = client.items._key("box", fields=COLLECTION_DETAIL_FIELDS)
    members_key = client.items._list_key(
        parent_id="box",
        item_types=None,
        fields=None,
        recursive=True,
        sort_by="SortName",
        sort_order="Ascending",
    )
    for key in (catalog_key, item_key, detail_key, members_key):
        save_json(key, {"cached": True})

    with patch.object(client, "_post"):
        client.collections.add_items("box", ["1"])

    for key in (catalog_key, item_key, detail_key, members_key):
        assert load_json(key) is None


def test_delete_collection_refuses_non_boxset():
    client = _client()
    with (
        patch.object(client.items, "get", return_value={"Id": "1", "Type": "Movie"}),
        patch.object(client.items, "delete") as delete,
    ):
        with pytest.raises(ValueError, match="expected BoxSet, got Movie"):
            client.collections.delete("1")
    delete.assert_not_called()


def test_delete_collection_checks_type_uncached_then_deletes():
    client = _client()
    with (
        patch.object(client.items, "get", return_value={"Id": "1", "Type": "BoxSet"}) as get,
        patch.object(client.items, "delete") as delete,
        patch.object(client.collections, "invalidate") as invalidate,
    ):
        client.collections.delete("1")
    get.assert_called_once_with("1", use_cache=False)
    delete.assert_called_once_with("1")
    invalidate.assert_called_once_with("1")


def test_items_merge_and_update_posts_full_merged_object():
    client = _client()
    detail = {"Id": "1", "Name": "Old", "Type": "BoxSet", "SortName": "Old"}
    with (
        patch.object(client.items, "get", return_value=dict(detail)) as get,
        patch.object(client.items, "update") as update,
    ):
        result = client.items.merge_and_update(
            "1",
            {"Name": "New", "ProductionYear": 1980},
        )
    get.assert_called_once_with("1", fields=None, use_cache=False)
    update.assert_called_once()
    payload = update.call_args.args[1]
    assert payload["Name"] == "New"
    assert payload["ProductionYear"] == 1980
    assert payload["SortName"] == "Old"
    assert result["Name"] == "New"
