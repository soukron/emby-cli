"""Tests for the version command."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import requests

from emby_cli.commands.version import cmd_version
from emby_cli.client import EmbyClient


def test_cmd_version_client_only(capsys):
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
    forbidden = MagicMock()
    forbidden.raise_for_status.side_effect = requests.HTTPError("403")
    # _request_with_retry raises HTTPError from raise_for_status
    public = MagicMock()
    public.json.return_value = {"ServerName": "home", "Version": "4.8.0"}

    def fake_get(path, **kwargs):
        if path == "/Users/Me":
            return me
        if path == "/System/Info":
            exc = requests.HTTPError("403")
            exc.response = MagicMock(status_code=403)
            raise exc
        if path == "/System/Info/Public":
            return public
        raise AssertionError(path)

    with patch.object(client, "_get", side_effect=fake_get):
        user, info = client.probe_session()
    assert user["Name"] == "u"
    assert info["ServerName"] == "home"
    assert info["Version"] == "4.8.0"
