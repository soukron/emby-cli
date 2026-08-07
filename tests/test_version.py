"""Tests for the version command."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import requests

from emby_cli.client import EmbyClient
from emby_cli.commands.version import cmd_version


def test_cmd_version_client_only(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    args = argparse.Namespace(server=None, api_key=None, username=None, password=None)
    with patch("emby_cli.commands.version.get_version", return_value="0.2.0"):
        cmd_version(args)
    out = capsys.readouterr().out
    assert out.strip() == "emby-cli: 0.2.0"


def test_cmd_version_with_server(capsys):
    args = argparse.Namespace(
        server="http://host:8096",
        api_key="k",
        username=None,
        password=None,
    )
    with patch("emby_cli.commands.version.get_version", return_value="0.2.0"):
        with patch("emby_cli.commands.version.EmbyClient") as cls:
            client = cls.return_value
            client.probe_session.return_value = (
                {"Name": "u"},
                {"Version": "4.8.10.0", "ServerName": "home"},
            )
            cmd_version(args)
    out = capsys.readouterr().out
    assert "emby-cli: 0.2.0" in out
    assert "server: 4.8.10.0 (home)" in out


def test_cmd_version_unreachable(capsys):
    args = argparse.Namespace(
        server="http://host:8096",
        api_key=None,
        username="u",
        password="bad",
    )
    with patch("emby_cli.commands.version.get_version", return_value="0.2.0"):
        with patch("emby_cli.commands.version.EmbyClient") as cls:
            client = cls.return_value
            client.probe_session.side_effect = requests.Timeout("timed out")
            cmd_version(args)
    out = capsys.readouterr().out
    assert "emby-cli: 0.2.0" in out
    assert "server: not validated (name and version unavailable)" in out


def test_get_system_info_endpoint():
    client = EmbyClient("http://host:8096", api_key="k")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Version": "4.8.0.0", "ServerName": "x"}
    with patch.object(client, "_get", return_value=mock_resp) as get:
        assert client.get_system_info()["Version"] == "4.8.0.0"
    assert get.call_args.args[0] == "/System/Info"


def test_probe_session_falls_back_to_public_system_info():
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "u1"
    me = MagicMock()
    me.json.return_value = {"Name": "u", "Id": "u1"}
    public = MagicMock()
    public.json.return_value = {"ServerName": "home", "Version": "4.8.0"}

    def fake_get(path, **kwargs):
        if path == "/Users/Me":
            return me
        if path == "/System/Info":
            raise requests.HTTPError("403")
        if path == "/System/Info/Public":
            return public
        raise AssertionError(path)

    with patch.object(client, "_get", side_effect=fake_get):
        user, info = client.probe_session()
    assert user["Name"] == "u"
    assert info["ServerName"] == "home"
    assert info["Version"] == "4.8.0"


def test_probe_session_uses_auth_user_skips_users_me(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    client = EmbyClient("http://host:8096")
    auth_user = {"Name": "u", "Id": "abcd" * 8}

    def fake_get(path, **kwargs):
        if path == "/Users/Me":
            raise AssertionError("/Users/Me should not be called after auth")
        if path == "/System/Info":
            resp = MagicMock()
            resp.json.return_value = {"ServerName": "home", "Version": "4.8"}
            return resp
        raise AssertionError(path)

    with patch.object(client, "authenticate", return_value=auth_user) as auth:
        with patch.object(client, "_get", side_effect=fake_get):
            user, info = client.probe_session(username="u", password="p")
    auth.assert_called_once()
    assert user is auth_user
    assert info["ServerName"] == "home"


def test_get_current_user_falls_back_to_users_id():
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid-1"
    by_id = MagicMock()
    by_id.json.return_value = {"Name": "u", "Id": "uid-1"}

    def fake_get(path, **kwargs):
        if path == "/Users/Me":
            raise requests.HTTPError("500 Guid")
        if path == "/Users/uid-1":
            return by_id
        raise AssertionError(path)

    with patch.object(client, "_get", side_effect=fake_get):
        assert client.get_current_user()["Name"] == "u"
