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

    def fake_auth(username, password, **kwargs):
        client.access_token = "new-tok"
        client.user_id = "uid-1"
        client._username = username
        client._password = password
        client._persist_auth_cache()
        return user

    with patch.object(client, "authenticate", side_effect=fake_auth) as auth:
        result = client.ensure_user_session("alice", "secret")
    auth.assert_called_once()
    assert result is user
    loaded = load_auth_cache(server_url="http://host:8096", username="alice")
    assert loaded is not None
    assert loaded.access_token == "new-tok"


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


def test_401_triggers_reauth_once(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = EmbyClient("http://host:8096")
    client.access_token = "stale"
    client.user_id = "uid-1"
    client._username = "alice"
    client._password = "secret"
    client._reauth_attempted = False

    unauthorized = MagicMock()
    unauthorized.status_code = 401
    unauthorized.raise_for_status.side_effect = requests.HTTPError(
        response=unauthorized
    )

    ok = MagicMock()
    ok.status_code = 200
    ok.raise_for_status.return_value = None

    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return unauthorized
        return ok

    with patch.object(client.session, "request", side_effect=fake_request):
        with patch.object(
            client,
            "authenticate",
            side_effect=lambda *a, **k: setattr(client, "access_token", "fresh")
            or {"Name": "alice", "Id": "uid-1"},
        ) as auth:
            resp = client._get("/Users/Me", retries=1)
    assert resp is ok
    auth.assert_called_once()
    assert client.access_token == "fresh"


def test_ensure_without_username_or_cache_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = EmbyClient("http://host:8096")
    with pytest.raises(RuntimeError, match="emby-cli login"):
        client.ensure_user_session(None, None)
