"""Tests for legacy command deprecation warnings."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from emby_cli.commands.download import cmd_download
from emby_cli.commands.play import cmd_play
from emby_cli.commands.search import cmd_search
from emby_cli.commands.show import cmd_show
from emby_cli.deprecation import warn_deprecated


def test_warn_deprecated_prints_to_stderr(capsys):
    warn_deprecated("search")
    captured = capsys.readouterr()
    assert "warning:" in captured.err
    assert "`search` is deprecated" in captured.err
    assert "item search" in captured.err
    assert captured.err.endswith("\n\n")


def test_cmd_play_warns(capsys):
    client = MagicMock()
    args = argparse.Namespace(
        item=None,
        search=None,
        id="123",
        pick_best_item=False,
        wait=False,
        player=None,
    )
    with patch("emby_cli.commands.play.find_player", return_value=["vlc"]):
        with patch("emby_cli.commands.play.play_item_ids", return_value=0):
            cmd_play(client, args)
    assert "`play` is deprecated" in capsys.readouterr().err


def test_cmd_show_warns(capsys):
    client = MagicMock()
    args = argparse.Namespace(item=None, library="", id="614156")
    with patch("emby_cli.commands.show._cmd_show_library"):
        cmd_show(client, args)
    assert "`show` is deprecated" in capsys.readouterr().err


def test_cmd_download_warns(capsys):
    client = MagicMock()
    args = argparse.Namespace(
        item="",
        library=None,
        from_file=None,
        id="123",
        search=None,
        pick_best_item=False,
        output="./downloads",
        force=False,
        throttle=0,
        method="download",
        dry_run=True,
        mirror_path=False,
        path_strip=None,
    )
    stats = MagicMock()
    stats.exit_code.return_value = 0
    with patch("emby_cli.commands.download.download_item_ids", return_value=stats):
        with pytest.raises(SystemExit) as exc:
            cmd_download(client, args)
    assert exc.value.code == 0
    assert "`download` is deprecated" in capsys.readouterr().err


def test_cmd_search_warns(capsys):
    client = MagicMock()
    client.no_data_cache = False
    args = argparse.Namespace(
        item="",
        library=None,
        id=None,
        search=None,
        query=None,
        count="all",
        item_type=None,
        year=None,
        order_by=None,
        desc=False,
        no_cache=False,
    )
    with patch("emby_cli.commands.search.fetch_item_listing", return_value=([], 0)):
        with patch("emby_cli.commands.search.mode_is_library", return_value=False):
            cmd_search(client, args)
    assert "`search` is deprecated" in capsys.readouterr().err
