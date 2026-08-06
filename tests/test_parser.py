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


def test_batch_requires_file():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--server", "http://x", "--api-key", "k", "batch"])
