"""Tests for unified auth.json store."""

from __future__ import annotations

import json
import stat

from emby_cli.auth_cache import (
    AuthCacheEntry,
    auth_store_path,
    clear_auth_cache,
    display_name,
    get_active_entry,
    list_auth_cache_entries,
    list_contexts,
    load_auth_cache,
    load_store,
    rename_context_alias,
    save_auth_cache,
    set_current_context,
    unique_cached_server_urls,
    upsert_context,
    validate_alias,
)


def test_auth_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    entry = AuthCacheEntry.create(
        "http://host:8096",
        "alice",
        "tok-1",
        "uid-1",
    )
    save_auth_cache(entry)
    path = auth_store_path()
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    loaded = load_auth_cache(server_url="http://host:8096", username="alice")
    assert loaded is not None
    assert loaded.access_token == "tok-1"
    assert loaded.name == "alice@http://host:8096"
    assert get_active_entry().name == loaded.name


def test_upsert_activates_context(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    save_auth_cache(
        AuthCacheEntry.create("http://b:8096", "bob", "tok-b", "uid-b")
    )
    active = get_active_entry()
    assert active is not None
    assert active.username == "bob"
    assert len(list_contexts()) == 2


def test_set_current_context(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    save_auth_cache(
        AuthCacheEntry.create("http://b:8096", "bob", "tok-b", "uid-b")
    )
    set_current_context("alice@http://a:8096")
    assert get_active_entry().username == "alice"


def test_set_current_context_by_unique_server(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    save_auth_cache(
        AuthCacheEntry.create("http://b:8096", "bob", "tok-b", "uid-b")
    )
    set_current_context("http://a:8096")
    assert get_active_entry().username == "alice"


def test_rename_context_alias_and_use_by_alias(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    save_auth_cache(
        AuthCacheEntry.create("http://b:8096", "bob", "tok-b", "uid-b")
    )
    entry = rename_context_alias("alice@http://a:8096", "home")
    assert display_name(entry) == "home"
    assert entry.name == "alice@http://a:8096"

    set_current_context("home")
    assert get_active_entry().name == "alice@http://a:8096"

    store = load_store()
    assert store.contexts[0].alias == "home" or store.contexts[1].alias == "home"


def test_upsert_preserves_alias(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    rename_context_alias("alice@http://a:8096", "home")
    upsert_context(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-new", "uid-a"),
        activate=True,
    )
    ctx = next(c for c in list_contexts() if c.username == "alice")
    assert ctx.alias == "home"
    assert ctx.access_token == "tok-new"


def test_validate_alias_rejects_whitespace_and_at(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    assert "whitespace" in validate_alias("my home")
    assert "@" in validate_alias("user@host")


def test_load_prefers_active_for_server(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    older = AuthCacheEntry.create("http://host:8096", "alice", "tok-a", "uid-a")
    older.saved_at = "2020-01-01T00:00:00+00:00"
    upsert_context(older, activate=True)
    newer = AuthCacheEntry.create("http://host:8096", "bob", "tok-b", "uid-b")
    newer.saved_at = "2024-01-01T00:00:00+00:00"
    upsert_context(newer, activate=False)
    set_current_context("alice@http://host:8096")
    loaded = load_auth_cache(server_url="http://host:8096", username=None)
    assert loaded is not None
    assert loaded.username == "alice"


def test_emby_no_auth_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("EMBY_NO_AUTH_CACHE", "1")
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "tok", "uid")
    )
    assert not auth_store_path().is_file()
    assert load_auth_cache(server_url="http://host:8096", username="alice") is None


def test_clear_auth_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "tok", "uid")
    )
    clear_auth_cache(server_url="http://host:8096", username="alice")
    assert load_auth_cache(server_url="http://host:8096", username="alice") is None
    assert get_active_entry() is None


def test_migrate_legacy_cache_files(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    legacy = tmp_path / "deadbeef.cache"
    legacy.write_text(
        json.dumps(
            {
                "server_url": "http://legacy:8096",
                "username": "alice",
                "access_token": "tok",
                "user_id": "uid",
                "saved_at": "2024-01-01T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    store = load_store()
    assert store.current_context == "alice@http://legacy:8096"
    assert len(store.contexts) == 1
    assert not legacy.is_file()
    assert auth_store_path().is_file()


def test_unique_cached_server_urls(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    upsert_context(
        AuthCacheEntry.create("http://a:8096", "bob", "tok-b", "uid-b"),
        activate=False,
    )
    save_auth_cache(
        AuthCacheEntry.create("http://b:8096", "carol", "tok-c", "uid-c")
    )
    assert unique_cached_server_urls() == ["http://a:8096", "http://b:8096"]
    assert len(list_auth_cache_entries()) == 3
