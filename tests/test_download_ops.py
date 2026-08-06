"""Tests for find_library helper."""

from __future__ import annotations

from emby_cli.download_ops import find_library


LIBS = [
    {"Id": "aaaaaaaa-1111", "Name": "Movies"},
    {"Id": "bbbbbbbb-2222", "Name": "TV"},
    {"Id": "cccccccc-3333", "Name": "Movies"},  # duplicate name
]


def test_find_library_by_exact_id():
    assert find_library(LIBS[:2], library_id="aaaaaaaa-1111")["Name"] == "Movies"


def test_find_library_by_unique_prefix():
    assert find_library(LIBS[:2], library_id="bbbb")["Name"] == "TV"


def test_find_library_by_name():
    assert find_library(LIBS[:2], name="movies")["Id"] == "aaaaaaaa-1111"


def test_find_library_ambiguous_name():
    assert find_library(LIBS, name="Movies") is None


def test_find_library_missing():
    assert find_library(LIBS[:2], name="Anime") is None
    assert find_library(LIBS[:2], library_id="zzzz") is None
