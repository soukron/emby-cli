"""Tests for argparse CLI surface."""

from __future__ import annotations

import pytest

from emby_cli.cli import build_parser


def test_build_parser_subcommands():
    parser = build_parser()
    subs = parser._subparsers._group_actions[0].choices
    assert set(subs) == {
        "list", "download", "search", "play", "sync", "batch", "version", "info",
    }


def test_parser_requires_command():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_download_defaults_output():
    parser = build_parser()
    args = parser.parse_args(["--server", "http://x", "--api-key", "k", "download", "-i", "abc"])
    assert args.output == "./downloads"
    assert args.method == "download"


def test_batch_has_pick_best_item():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "batch", "-F", "titles.txt", "--pick-best-item",
    ])
    assert args.pick_best_item is True


def test_batch_pick_best_default_false():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "batch", "-F", "titles.txt",
    ])
    assert args.pick_best_item is False


def test_batch_requires_file():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--server", "http://x", "--api-key", "k", "batch"])


def test_search_count_default_none():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k", "search", "matrix",
    ])
    assert args.count is None


def test_search_count_flag():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "matrix", "--count", "50",
    ])
    assert args.count == 50


def test_version_subcommand_parses_without_server(monkeypatch):
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    monkeypatch.delenv("EMBY_API_KEY", raising=False)
    monkeypatch.delenv("EMBY_USERNAME", raising=False)
    monkeypatch.delenv("EMBY_PASSWORD", raising=False)
    parser = build_parser()
    args = parser.parse_args(["version"])
    assert args.command == "version"
    assert args.server is None
