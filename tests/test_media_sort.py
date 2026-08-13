"""Tests for media item sorting helpers."""

from __future__ import annotations

from emby_cli.api.items import ItemsService
from emby_cli.media_sort import sort_media_items


def test_emby_sort_maps_release_date_and_added_date():
    assert ItemsService._emby_sort("release-date", desc=False) == (
        "PremiereDate,SortName",
        "Ascending",
    )
    assert ItemsService._emby_sort("added-date", desc=True) == (
        "DateCreated,SortName",
        "Descending",
    )
    assert ItemsService._emby_sort("year", desc=False) == ("ProductionYear,SortName", "Ascending")
    assert ItemsService._emby_sort("name", desc=True) == ("SortName", "Descending")
    assert ItemsService._emby_sort(None, desc=False) == ("DateCreated,SortName", "Descending")
    assert ItemsService._emby_sort("id", desc=True) == ("SortName", "Ascending")
    assert ItemsService._emby_sort("resolution", desc=True) == (
        "Resolution,SortName",
        "Descending",
    )
    assert ItemsService._emby_sort("size", desc=True) == ("Size,SortName", "Descending")


def test_sort_media_items_by_id():
    items = [
        {"Id": "100", "Name": "B"},
        {"Id": "2", "Name": "A"},
    ]
    ordered = sort_media_items(items, "id", desc=False)
    assert [item["Id"] for item in ordered] == ["2", "100"]
