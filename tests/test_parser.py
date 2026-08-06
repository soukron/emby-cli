"""Tests for argparse CLI surface."""

from __future__ import annotations

import pytest

from emby_cli.cli import build_parser


def test_build_parser_subcommands():
    parser = build_parser()
    subs = parser._subparsers._group_actions[0].choices
    assert set(subs) == {"list", "download", "search", "play", "sync", "batch"}


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
        "batch", "-F", "titles.txt", "--pick-best-item", "1",
    ])
    assert args.pick_best_item == 1


def test_batch_pick_best_default_zero():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "batch", "-F", "titles.txt",
    ])
    assert args.pick_best_item == 0


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
