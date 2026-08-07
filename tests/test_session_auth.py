"""Tests for ensure_user_session and 401 re-auth."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from emby_cli.auth_cache import AuthCacheEntry, load_auth_cache, save_auth_cache
from emby_cli.client import EmbyClient


def test_ensure_restores_cache_without_authenticate(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "cached-tok", "uid-1")
    )
    client = EmbyClient("http://host:8096")
    with patch.object(client, "authenticate") as auth:
        result = client.ensure_user_session("alice", "secret")
    auth.assert_not_called()
    assert result is None
    assert client.access_token == "cached-tok"
    assert client.user_id == "uid-1"
    assert client._password == "secret"


def test_ensure_authenticates_on_cache_miss(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = EmbyClient("http://host:8096")
    user = {"Name": "alice", "Id": "uid-1"}

    with patch.object(client, "authenticate", return_value=user) as auth:
        result = client.ensure_user_session("alice", "secret")
    auth.assert_called_once_with("alice", "secret", timeout=None, retries=None)
    assert result is user
    # Persistence is authenticate()'s job — covered by test_authenticate_persists_cache.
    assert load_auth_cache(server_url="http://host:8096", username="alice") is None


def test_ensure_force_always_authenticates(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "cached-tok", "uid-1")
    )
    client = EmbyClient("http://host:8096")
    with patch.object(
        client, "authenticate", return_value={"Name": "alice", "Id": "uid-1"}
    ) as auth:
        client.ensure_user_session("alice", "secret", force=True)
    auth.assert_called_once()


def test_authenticate_persists_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = EmbyClient("http://host:8096")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "AccessToken": "tok-xyz",
        "User": {"Name": "alice", "Id": "uid-1"},
    }
    with patch.object(client, "_post", return_value=mock_resp):
        client.authenticate("alice", "secret")
    loaded = load_auth_cache(server_url="http://host:8096", username="alice")
    assert loaded is not None
    assert loaded.access_token == "tok-xyz"


def test_401_triggers_reauth_and_clears_cache(tmp_path, monkeypatch):
    """401 on an operational call invalidates cache then re-authenticates once."""
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "stale", "uid-1")
    )
    client = EmbyClient("http://host:8096")
    client.access_token = "stale"
    client.user_id = "uid-1"
    client._username = "alice"
    client._password = "secret"

    unauthorized = MagicMock()
    unauthorized.status_code = 401
    unauthorized.raise_for_status.side_effect = requests.HTTPError(
        response=unauthorized
    )
    auth_ok = MagicMock()
    auth_ok.status_code = 200
    auth_ok.raise_for_status.return_value = None
    auth_ok.json.return_value = {
        "AccessToken": "fresh",
        "User": {"Name": "alice", "Id": "uid-1"},
    }
    ok = MagicMock()
    ok.status_code = 200
    ok.raise_for_status.return_value = None

    from emby_cli.auth_cache import clear_auth_cache as real_clear

    with (
        patch.object(
            client.session,
            "request",
            side_effect=[unauthorized, auth_ok, ok],
        ) as req,
        patch("emby_cli.client.clear_auth_cache", wraps=real_clear) as clear_cache,
    ):
        resp = client._get("/Users/Me", retries=1)

    assert resp is ok
    assert client.access_token == "fresh"
    assert req.call_count == 3
    clear_cache.assert_called_once_with(
        server_url="http://host:8096", username="alice"
    )
    loaded = load_auth_cache(server_url="http://host:8096", username="alice")
    assert loaded is not None
    assert loaded.access_token == "fresh"


def test_ensure_without_username_or_cache_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = EmbyClient("http://host:8096")
    with pytest.raises(RuntimeError, match="emby-cli login"):
        client.ensure_user_session(None, None)
