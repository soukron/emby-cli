"""Tests for play multi-id support."""

from __future__ import annotations

import argparse
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from emby_cli import item_ops
from emby_cli.commands import play as play_mod


def test_play_csv_ids_launches_each(capsys):
    client = MagicMock()
    client.get_item_info.side_effect = [
        {"Id": "1", "Name": "A", "Type": "Movie", "ProductionYear": 2001},
        {"Id": "2", "Name": "B", "Type": "Movie", "ProductionYear": 2002},
    ]
    client.resolve_direct_stream_url.side_effect = ["http://u/1", "http://u/2"]
    args = argparse.Namespace(
        item=None,
        id="1,2",
        search=None,
        pick_best_item=False,
        player="vlc",
        wait=False,
    )
    with patch.object(play_mod, "find_player", return_value=["vlc"]):
        with patch.object(item_ops, "play_url", return_value=0) as play_url:
            play_mod.cmd_play(client, args)
    assert play_url.call_count == 2
    assert play_url.call_args_list[0].args[1] == "http://u/1"
    assert play_url.call_args_list[1].args[1] == "http://u/2"
    out = capsys.readouterr().out
    assert "[1/2] Playing: A" in out
    assert "[2/2] Playing: B" in out


def test_play_csv_continues_after_fetch_error(capsys):
    client = MagicMock()

    def get_info(iid):
        if iid == "bad":
            raise RuntimeError("gone")
        return {"Id": iid, "Name": "Ok", "Type": "Movie", "ProductionYear": 2000}

    client.get_item_info.side_effect = get_info
    client.resolve_direct_stream_url.return_value = "http://u/ok"
    args = argparse.Namespace(
        item=None,
        id="bad,ok",
        search=None,
        pick_best_item=False,
        player="vlc",
        wait=False,
    )
    with patch.object(play_mod, "find_player", return_value=["vlc"]):
        with patch.object(item_ops, "play_url", return_value=0) as play_url:
            with pytest.raises(SystemExit) as exc:
                play_mod.cmd_play(client, args)
    assert exc.value.code == 1
    assert play_url.call_count == 1
    captured = capsys.readouterr()
    assert "fetching item bad" in captured.err
    assert "Playing: Ok" in captured.out


def test_play_items_launches_each(capsys):
    client = MagicMock()
    items = [
        {"Id": "1", "Name": "A", "Type": "Movie", "ProductionYear": 2001},
        {"Id": "2", "Name": "B", "Type": "Episode", "ProductionYear": 2002},
    ]
    client.resolve_direct_stream_url.side_effect = ["http://u/1", "http://u/2"]
    with patch.object(item_ops, "play_url", return_value=0) as play_url:
        rc = item_ops.play_items(client, items, ["vlc"], wait=False, show_progress=True)
    assert rc == 0
    assert play_url.call_count == 2
    out = capsys.readouterr().out
    assert "[1/2] Playing: A" in out
    assert "[2/2] Playing: B" in out


def test_play_url_wait_suppresses_player_output():
    with patch("emby_cli.item_ops.subprocess.run", return_value=MagicMock(returncode=0)) as run:
        rc = item_ops.play_url(["vlc"], "http://u/1", wait=True)
    assert rc == 0
    assert run.call_args.kwargs["stdin"] is subprocess.DEVNULL
    assert run.call_args.kwargs["stdout"] is subprocess.DEVNULL
    assert run.call_args.kwargs["stderr"] is subprocess.DEVNULL
