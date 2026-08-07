"""Tests for item/library table output."""

from __future__ import annotations

from emby_cli.resolve import (
    print_available_libraries,
    print_item_choices,
    print_library_choices,
    sort_for_display,
)


def test_sort_for_display_id_desc_then_name():
    rows = [
        {"Id": "10", "Name": "Zebra"},
        {"Id": "100", "Name": "Alpha"},
        {"Id": "100", "Name": "Beta"},
        {"Id": "2", "Name": "Middle"},
    ]
    sorted_rows = sort_for_display(rows)
    assert [r["Id"] for r in sorted_rows] == ["100", "100", "10", "2"]
    assert [r["Name"] for r in sorted_rows] == ["Alpha", "Beta", "Zebra", "Middle"]


def test_print_item_choices_orders_by_id_desc(capsys):
    print_item_choices([
        {
            "Id": "10",
            "Name": "Older",
            "Type": "Movie",
            "ProductionYear": 2010,
            "Width": 1920,
            "Size": 1024,
        },
        {
            "Id": "20",
            "Name": "Newer",
            "Type": "Movie",
            "ProductionYear": 2020,
            "Width": 1920,
            "Size": 2048,
        },
    ])
    out = capsys.readouterr().out
    assert out.index("20") < out.index("10")
    assert "Newer" in out and "Older" in out


def test_print_item_choices_media(capsys):
    print_item_choices([
        {
            "Id": "abc",
            "Name": "Film",
            "Type": "Movie",
            "ProductionYear": 2020,
            "Width": 1920,
            "Size": 1024,
        },
    ])
    out = capsys.readouterr().out
    assert "ID" in out and "Name" in out and "Year" in out and "Size" in out
    assert "abc" in out
    assert "Film" in out
    assert "Movie" in out


def test_print_library_choices(capsys):
    print_library_choices([
        {
            "Id": "5",
            "Name": "TV",
            "Type": "tvshows",
            "ItemCount": 10,
        },
        {
            "Id": "lib1",
            "Name": "Movies",
            "Type": "movies",
            "ItemCount": 42,
        },
        {
            "Id": "9",
            "Name": "Music",
            "Type": "music",
            "ItemCount": 3,
        },
    ])
    out = capsys.readouterr().out
    assert "Items" in out
    assert "Year" not in out
    assert "Res" not in out
    assert "Size" not in out
    assert out.index("9") < out.index("5")
    assert "Movies" in out
    assert "42" in out


def test_print_available_libraries_sorted(capsys):
    print_available_libraries([
        {"Id": "3", "Name": "C"},
        {"Id": "10", "Name": "A"},
        {"Id": "10", "Name": "B"},
    ])
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert lines[0].startswith("  - [10] A")
    assert lines[1].startswith("  - [10] B")
    assert lines[2].startswith("  - [3] C")
