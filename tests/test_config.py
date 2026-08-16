"""Tests for emby-cli config subcommands."""

from __future__ import annotations

import argparse

import pytest

from emby_cli.auth_cache import AuthCacheEntry, save_auth_cache, upsert_context
from emby_cli.commands.config import (
    cmd_config_current_server,
    cmd_config_get_servers,
    cmd_config_rename_server,
    cmd_config_use_server,
    cmd_config_view,
)


def test_config_current_server(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "tok", "uid")
    )
    cmd_config_current_server(argparse.Namespace())
    assert capsys.readouterr().out.strip() == "alice@http://host:8096"


def test_config_current_server_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        cmd_config_current_server(argparse.Namespace())
    assert exc.value.code == 1


def test_config_get_servers(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    upsert_context(
        AuthCacheEntry.create("http://b:8096", "bob", "tok-b", "uid-b"),
        activate=True,
    )
    cmd_config_get_servers(argparse.Namespace())
    out = capsys.readouterr().out
    assert "CURRENT" in out
    assert "bob@http://b:8096" in out
    assert "*" in out


def test_config_use_server(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    save_auth_cache(
        AuthCacheEntry.create("http://b:8096", "bob", "tok-b", "uid-b")
    )
    cmd_config_use_server(argparse.Namespace(server_name="alice@http://a:8096"))
    assert "Switched to server alice@http://a:8096" in capsys.readouterr().out
    cmd_config_current_server(argparse.Namespace())
    assert capsys.readouterr().out.strip() == "alice@http://a:8096"


def test_config_rename_and_use_alias(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create(
            "http://emby.villageek.gmbros.net",
            "media",
            "tok-a",
            "uid-a",
        )
    )
    save_auth_cache(
        AuthCacheEntry.create(
            "http://sniperembyp7p8.zapto.org:8096",
            "Rbembypr022",
            "tok-b",
            "uid-b",
        )
    )
    cmd_config_rename_server(
        argparse.Namespace(
            server_name="media@http://emby.villageek.gmbros.net",
            new_name="synology",
        )
    )
    assert (
        'Renamed server "media@http://emby.villageek.gmbros.net" to "synology"'
        in capsys.readouterr().out
    )

    cmd_config_get_servers(argparse.Namespace())
    out = capsys.readouterr().out
    assert "synology" in out
    assert "media@http://emby.villageek.gmbros.net" not in out.split("SERVER")[0]

    cmd_config_use_server(argparse.Namespace(server_name="synology"))
    assert (
        'Switched to server "synology" (media@http://emby.villageek.gmbros.net)'
        in capsys.readouterr().out
    )
    cmd_config_current_server(argparse.Namespace())
    assert capsys.readouterr().out.strip() == "synology"


def test_config_rename_server_duplicate_alias(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://a:8096", "alice", "tok-a", "uid-a")
    )
    save_auth_cache(
        AuthCacheEntry.create("http://b:8096", "bob", "tok-b", "uid-b")
    )
    cmd_config_rename_server(
        argparse.Namespace(
            server_name="alice@http://a:8096",
            new_name="home",
        )
    )
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        cmd_config_rename_server(
            argparse.Namespace(
                server_name="bob@http://b:8096",
                new_name="home",
            )
        )
    assert exc.value.code == 1
    assert "already used" in capsys.readouterr().err


def test_config_view_redacts_token(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "secret-token", "uid")
    )
    cmd_config_view(argparse.Namespace())
    out = capsys.readouterr().out
    assert "secret-token" not in out
    assert '"access_token": "***"' in out
    assert "alice@http://host:8096" in out
