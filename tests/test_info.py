"""Tests for the info command."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest
import requests

from emby_cli.client import EmbyClient
from emby_cli.commands.info import cmd_info


def test_info_requires_server(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    args = argparse.Namespace(server=None, api_key="k", username=None, password=None)
    with pytest.raises(SystemExit) as exc:
        cmd_info(args)
    assert exc.value.code == 1


def test_info_ok(capsys):
    args = argparse.Namespace(
        server="http://host:8096",
        api_key="k",
        username=None,
        password=None,
    )
    with patch("emby_cli.commands.info.EmbyClient") as cls:
        client = cls.return_value
        client.server_url = "http://host:8096"
        client.probe_session.return_value = (
            {"Name": "sergio", "Id": "u1"},
            {
                "ServerName": "home",
                "Version": "4.8.0",
                "OperatingSystemDisplayName": "Linux",
                "Id": "srv-id",
                "LocalAddress": "http://192.168.1.1:8096",
                "WanAddress": "http://example.com:8096",
                "HasUpdateAvailable": False,
            },
        )
        client.get_libraries.return_value = [
            {"Name": "Movies", "Id": "1"},
            {"Name": "TV", "Id": "2"},
        ]
        client.get_item_counts.return_value = {
            "MovieCount": 10,
            "SeriesCount": 2,
            "EpisodeCount": 50,
            "SongCount": 0,
            "AlbumCount": 0,
            "BoxSetCount": 3,
            "BookCount": 0,
        }
        cmd_info(args)

    out = capsys.readouterr().out
    assert "Connection" in out
    assert "user: sergio" in out
    assert "url: http://host:8096" in out
    assert "Server" in out
    assert "server: home" in out
    assert "version: 4.8.0" in out
    assert "os: Linux" in out
    assert "id: srv-id" in out
    assert "local: http://192.168.1.1:8096" in out
    assert "wan: http://example.com:8096" in out
    assert "Content" in out
    assert "libraries: 2" in out
    assert "Movies" not in out
    assert "movies: 10" in out
    assert "series: 2" in out
    assert "episodes: 50" in out
    assert "songs: 0" in out
    assert "albums: 0" in out
    assert "boxsets: 3" in out
    assert "books:" not in out
    assert client.get_item_counts.call_args.kwargs["user_id"] == "u1"


def test_info_unreachable_soft(capsys):
    args = argparse.Namespace(
        server="http://host:8096",
        api_key=None,
        username="u",
        password="bad",
    )
    with patch("emby_cli.commands.info.EmbyClient") as cls:
        client = cls.return_value
        client.server_url = "http://host:8096"
        client.probe_session.side_effect = requests.Timeout("timed out")
        cmd_info(args)
    out = capsys.readouterr().out
    assert "Connection" in out
    assert "user: u" in out
    assert "url: http://host:8096" in out
    assert "Server" in out
    assert "server: not validated (name and version unavailable)" in out
    assert "movies:" not in out


def test_get_item_counts_endpoint():
    client = EmbyClient("http://host:8096", api_key="k")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"MovieCount": 1}
    with patch.object(client, "_get", return_value=mock_resp) as get:
        assert client.get_item_counts(user_id="uid")["MovieCount"] == 1
    assert get.call_args.args[0] == "/Items/Counts"
    assert get.call_args.kwargs["params"]["UserId"] == "uid"
