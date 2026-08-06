"""Tests for AccessToken auth cache."""

from __future__ import annotations

import stat

from emby_cli.auth_cache import (
    AuthCacheEntry,
    auth_cache_file,
    clear_auth_cache,
    list_auth_cache_entries,
    load_auth_cache,
    save_auth_cache,
    unique_cached_server_urls,
)


def test_auth_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    entry = AuthCacheEntry.create(
        "http://host:8096",
        "alice",
        "tok-1",
        "uid-1",
    )
    save_auth_cache(entry)
    path = auth_cache_file("http://host:8096", "alice")
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    loaded = load_auth_cache(server_url="http://host:8096", username="alice")
    assert loaded is not None
    assert loaded.access_token == "tok-1"
    assert loaded.user_id == "uid-1"
    assert loaded.username == "alice"


def test_auth_cache_rejects_mismatched_server(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok", "uid")
    )
    assert load_auth_cache(server_url="http://b:8096", username="alice") is None


def test_auth_cache_rejects_mismatched_user(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "tok", "uid")
    )
    assert load_auth_cache(server_url="http://host:8096", username="bob") is None


def test_auth_cache_find_latest_without_username(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    older = AuthCacheEntry.create("http://host:8096", "alice", "tok-a", "uid-a")
    older.saved_at = "2020-01-01T00:00:00+00:00"
    save_auth_cache(older)
    newer = AuthCacheEntry.create("http://host:8096", "bob", "tok-b", "uid-b")
    newer.saved_at = "2024-01-01T00:00:00+00:00"
    save_auth_cache(newer)

    loaded = load_auth_cache(server_url="http://host:8096", username=None)
    assert loaded is not None
    assert loaded.username == "bob"
    assert loaded.access_token == "tok-b"


def test_emby_no_auth_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("EMBY_NO_AUTH_CACHE", "1")
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "tok", "uid")
    )
    assert list(tmp_path.glob("*.cache")) == []
    assert load_auth_cache(server_url="http://host:8096", username="alice") is None


def test_clear_auth_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "tok", "uid")
    )
    clear_auth_cache(server_url="http://host:8096", username="alice")
    assert load_auth_cache(server_url="http://host:8096", username="alice") is None


def test_auth_cache_file_stable(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    a = auth_cache_file("http://host:8096/", "alice")
    b = auth_cache_file("http://host:8096", "alice")
    assert a == b
    assert a.suffix == ".cache"


def test_unique_cached_server_urls(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "bob", "tok-b", "uid-b")
    )
    save_auth_cache(
        AuthCacheEntry.create("http://b:8096", "carol", "tok-c", "uid-c")
    )
    assert unique_cached_server_urls() == ["http://a:8096", "http://b:8096"]
    assert len(list_auth_cache_entries()) == 3
