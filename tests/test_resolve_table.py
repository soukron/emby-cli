"""Tests for item/library table output."""

from __future__ import annotations

from emby_cli.resolve import print_item_choices, print_library_choices


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
            "Id": "lib1",
            "Name": "Movies",
            "Type": "movies",
            "ItemCount": 42,
        },
    ])
    out = capsys.readouterr().out
    assert "Items" in out
    assert "Year" not in out
    assert "Res" not in out
    assert "Size" not in out
    assert "lib1" in out
    assert "Movies" in out
    assert "42" in out
