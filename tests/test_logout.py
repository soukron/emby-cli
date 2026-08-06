"""Tests for logout command and session revoke."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest
import requests

from emby_cli.auth_cache import AuthCacheEntry, load_auth_cache, save_auth_cache
from emby_cli.client import EmbyClient
from emby_cli.commands.logout import cmd_logout


def test_logout_session_posts_endpoint():
    client = EmbyClient("http://host:8096", use_auth_cache=False)
    client.access_token = "tok"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    with patch.object(client, "_post", return_value=mock_resp) as post:
        client.logout_session()
    post.assert_called_once()
    assert post.call_args.args[0] == "/Sessions/Logout"


def test_logout_session_ignores_401():
    client = EmbyClient("http://host:8096", use_auth_cache=False)
    client.access_token = "stale"
    err = requests.HTTPError()
    err.response = MagicMock(status_code=401)
    with patch.object(client, "_post", side_effect=err):
        client.logout_session()


def test_cmd_logout_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "tok", "uid")
    )
    args = argparse.Namespace(
        server=None,
        api_key=None,
        username=None,
        password=None,
    )
    with patch.object(EmbyClient, "logout_session") as logout:
        cmd_logout(args)
    logout.assert_called_once()
    assert load_auth_cache(server_url="http://host:8096", username="alice") is None
    out = capsys.readouterr().out
    assert "Logged out alice @ http://host:8096" in out


def test_cmd_logout_no_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    args = argparse.Namespace(
        server=None,
        api_key=None,
        username=None,
        password=None,
    )
    with pytest.raises(SystemExit) as exc:
        cmd_logout(args)
    assert exc.value.code == 1


def test_cmd_logout_clears_when_revoke_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "tok", "uid")
    )
    args = argparse.Namespace(
        server=None,
        api_key=None,
        username=None,
        password=None,
    )
    with patch.object(
        EmbyClient, "logout_session", side_effect=requests.Timeout("down")
    ):
        cmd_logout(args)
    captured = capsys.readouterr()
    assert load_auth_cache(server_url="http://host:8096", username="alice") is None
    assert "could not revoke token" in captured.err
    assert "Logged out alice @ http://host:8096" in captured.out
