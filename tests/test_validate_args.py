"""Selector validation runs before authentication."""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from emby_cli.cli import main
from emby_cli.commands.download import validate_download_args
from emby_cli.commands.play import validate_play_args
from emby_cli.commands.search import validate_search_args


def test_validate_search_requires_exactly_one_selector():
    args = argparse.Namespace(
        library=True,
        media_item=False,
        id=None,
        search=None,
        all=False,
        count=30,
    )
    assert validate_search_args(args) == (
        "Provide exactly one of --id, --search, or --all"
    )


def test_validate_search_ok():
    args = argparse.Namespace(
        library=True,
        media_item=False,
        id=None,
        search=None,
        all=True,
        count=30,
    )
    assert validate_search_args(args) is None


def test_validate_search_count_positive():
    args = argparse.Namespace(
        library=False,
        media_item=True,
        id=None,
        search="x",
        all=False,
        count=0,
    )
    assert validate_search_args(args) == "error: --count must be >= 1"


def test_validate_download_media_item_needs_selector(monkeypatch):
    monkeypatch.delenv("EMBY_ITEM_ID", raising=False)
    args = argparse.Namespace(
        media_item=True,
        library=False,
        from_file=None,
        id=None,
        search=None,
        pick_best_item=False,
    )
    assert validate_download_args(args) == (
        "With --media-item, provide exactly one of --id or --search"
    )


def test_validate_download_library_rejects_pick_best():
    args = argparse.Namespace(
        media_item=False,
        library=True,
        from_file=None,
        id="1",
        search=None,
        pick_best_item=True,
    )
    assert validate_download_args(args) == (
        "--pick-best-item cannot be used with --library"
    )


def test_validate_download_from_file_rejects_id():
    args = argparse.Namespace(
        media_item=False,
        library=False,
        from_file="titles.txt",
        id="1",
        search=None,
        pick_best_item=False,
    )
    assert validate_download_args(args) == (
        "With --from-file, do not pass --id or --search"
    )


def test_validate_play_needs_selector(monkeypatch):
    monkeypatch.delenv("EMBY_ITEM_ID", raising=False)
    args = argparse.Namespace(id=None, search=None, pick_best_item=False)
    assert validate_play_args(args) == "Provide exactly one of --id or --search"


def test_validate_play_pick_best_only_with_search():
    args = argparse.Namespace(id="1", search=None, pick_best_item=True)
    assert validate_play_args(args) == (
        "--pick-best-item can only be used with --search"
    )


def test_main_search_library_without_selector_skips_auth(capsys, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["emby-cli", "--server", "http://x", "--api-key", "k", "search", "--library"],
    )
    with patch("emby_cli.cli._open_client") as open_client:
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    open_client.assert_not_called()
    out = capsys.readouterr().out
    assert "Provide exactly one of --id, --search, or --all" in out


def test_main_download_library_without_selector_skips_auth(capsys, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "emby-cli",
            "--server", "http://x",
            "--username", "u",
            "--password", "p",
            "download", "--library",
        ],
    )
    with patch("emby_cli.cli._open_client") as open_client:
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    open_client.assert_not_called()
    assert "With --library, provide exactly one of --id or --search" in (
        capsys.readouterr().out
    )


def test_main_play_without_selector_skips_auth(capsys, monkeypatch):
    monkeypatch.delenv("EMBY_ITEM_ID", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        ["emby-cli", "--server", "http://x", "--api-key", "k", "play"],
    )
    with patch("emby_cli.cli._open_client") as open_client:
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    open_client.assert_not_called()
    assert "Provide exactly one of --id or --search" in capsys.readouterr().out
