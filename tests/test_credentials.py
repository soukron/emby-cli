"""Tests for credential resolution and login command."""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from emby_cli.commands.login import cmd_login
from emby_cli.credentials import (
    CredentialError,
    resolve_login_credentials,
    resolve_password,
    resolve_server,
    resolve_username,
)


def test_resolve_server_from_args():
    args = argparse.Namespace(server="http://x:8096/")
    assert resolve_server(args) == "http://x:8096"


def test_resolve_server_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    args = argparse.Namespace(server=None)
    with pytest.raises(CredentialError, match="EMBY_SERVER"):
        resolve_server(args, prompt=False)


def test_resolve_server_from_active_context(tmp_path, monkeypatch):
    from emby_cli.auth_cache import AuthCacheEntry, save_auth_cache, upsert_context

    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    upsert_context(
        AuthCacheEntry.create("http://b:8096", "bob", "tok-b", "uid-b"),
        activate=True,
    )
    args = argparse.Namespace(server=None)
    assert resolve_server(args, prompt=False) == "http://b:8096"


def test_resolve_server_ignores_inactive_without_flag(tmp_path, monkeypatch):
    from emby_cli.auth_cache import AuthCacheEntry, save_auth_cache, set_current_context

    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    save_auth_cache(
        AuthCacheEntry.create("http://b:8096", "bob", "tok-b", "uid-b")
    )
    set_current_context("alice@http://a:8096")
    args = argparse.Namespace(server=None)
    assert resolve_server(args, prompt=False) == "http://a:8096"


def test_resolve_password_none_when_unset(monkeypatch):
    monkeypatch.delenv("EMBY_PASSWORD", raising=False)
    args = argparse.Namespace(password=None)
    assert resolve_password(args, prompt=False) is None


def test_resolve_password_empty_string_from_args():
    args = argparse.Namespace(password="")
    assert resolve_password(args, prompt=False) == ""


def test_resolve_login_prompts(monkeypatch):
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    monkeypatch.delenv("EMBY_USERNAME", raising=False)
    monkeypatch.delenv("EMBY_PASSWORD", raising=False)
    args = argparse.Namespace(server=None, username=None, password=None)
    with patch("emby_cli.credentials.sys.stdin.isatty", return_value=True):
        with patch("emby_cli.credentials.input", side_effect=["http://s", "alice"]):
            with patch("emby_cli.credentials.getpass", return_value="secret"):
                server, user, pw = resolve_login_credentials(args)
    assert server == "http://s"
    assert user == "alice"
    assert pw == "secret"


def test_resolve_login_no_tty_missing_password(monkeypatch):
    monkeypatch.delenv("EMBY_PASSWORD", raising=False)
    args = argparse.Namespace(
        server="http://s",
        username="alice",
        password=None,
    )
    with patch("emby_cli.credentials.sys.stdin.isatty", return_value=False):
        with pytest.raises(CredentialError, match="EMBY_PASSWORD"):
            resolve_login_credentials(args)


def test_cmd_login_success(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    args = argparse.Namespace(
        server="http://host:8096",
        username="alice",
        password="secret",
        api_key=None,
    )
    with patch("emby_cli.commands.login.EmbyClient") as cls:
        client = cls.return_value
        client.server_url = "http://host:8096"
        client.ensure_user_session.return_value = {"Name": "alice", "Id": "u1"}
        cmd_login(args)
    client.ensure_user_session.assert_called_once_with(
        "alice", "secret", force=True
    )
    out = capsys.readouterr().out
    assert "Logged in as alice @ http://host:8096" in out


def test_resolve_username_from_env(monkeypatch):
    monkeypatch.setenv("EMBY_USERNAME", "from-env")
    args = argparse.Namespace(username=None)
    assert resolve_username(args) == "from-env"
