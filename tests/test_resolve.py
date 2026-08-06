"""Tests for title parsing and resolution ranking."""

from __future__ import annotations

from emby_cli.resolve import (
    classify_resolution,
    parse_title_line,
    pick_best_item,
)


def test_parse_title_plain():
    assert parse_title_line("Inception") == ("Inception", None, None, None)


def test_parse_title_year():
    assert parse_title_line("Inception (2010)") == ("Inception", None, None, 2010)


def test_parse_title_season_episode():
    assert parse_title_line("Show (2008) S01E05") == ("Show", 1, 5, 2008)


def test_parse_title_season_only():
    assert parse_title_line("Show S02") == ("Show", 2, None, None)


def test_classify_resolution():
    assert classify_resolution(None) == "?"
    assert classify_resolution(3840) == "4K"
    assert classify_resolution(1920) == "1080p"
    assert classify_resolution(1280) == "720p"
    assert classify_resolution(720) == "SD"


def test_pick_best_prefers_1080p():
    items = [
        {"Id": "4k", "Width": 3840},
        {"Id": "1080", "Width": 1920},
        {"Id": "720", "Width": 1280},
    ]
    best = pick_best_item(items)
    assert best["Id"] == "1080"


def test_pick_best_single():
    items = [{"Id": "only", "Width": 3840}]
    assert pick_best_item(items)["Id"] == "only"


def test_pick_best_empty():
    assert pick_best_item([]) is None
