"""Tests for exact metadata-cache invalidation."""

from __future__ import annotations

from emby_cli.data_cache import delete_json, load_json, save_json


def test_delete_json_removes_exact_key(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_json("one", {"Id": "1"})
    save_json("two", {"Id": "2"})

    delete_json("one")

    assert load_json("one") is None
    assert load_json("two") == {"Id": "2"}


def test_delete_json_missing_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    delete_json("missing")
