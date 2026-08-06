"""Tests for argparse CLI surface."""

from __future__ import annotations

import pytest

from emby_cli.cli import build_parser


def test_build_parser_subcommands():
    parser = build_parser()
    subs = parser._subparsers._group_actions[0].choices
    assert set(subs) == {
        "help", "login", "logout", "config", "download", "search", "play", "version", "info",
    }


def test_help_subcommand_parses_without_server(monkeypatch):
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    monkeypatch.delenv("EMBY_API_KEY", raising=False)
    monkeypatch.delenv("EMBY_USERNAME", raising=False)
    monkeypatch.delenv("EMBY_PASSWORD", raising=False)
    parser = build_parser()
    args = parser.parse_args(["help"])
    assert args.command == "help"


def test_parser_requires_command():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_download_item_id():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "download", "--media-item", "--id", "abc",
    ])
    assert args.media_item is True
    assert args.id == "abc"
    assert args.output == "./downloads"
    assert args.method == "download"
    assert args.dry_run is False


def test_download_item_search_pick_best():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "download", "--media-item", "--search", "Show S01E01", "--pick-best-item",
    ])
    assert args.media_item is True
    assert args.search == "Show S01E01"
    assert args.pick_best_item is True


def test_download_library_search():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "download", "--library", "--search", "Movies",
    ])
    assert args.library is True
    assert args.search == "Movies"


def test_download_from_file_dry_run():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "download", "--from-file", "titles.txt", "--dry-run",
    ])
    assert args.from_file == "titles.txt"
    assert args.dry_run is True
    assert args.pick_best_item is False


def test_download_requires_mode():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--server", "http://x", "--api-key", "k", "download",
        ])


def test_download_modes_exclusive():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--server", "http://x", "--api-key", "k",
            "download", "--media-item", "--library", "--id", "x",
        ])


def test_play_id():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "play", "--id", "abc",
    ])
    assert args.id == "abc"
    assert args.search is None


def test_play_search_pick_best():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "play", "--search", "Movie (2010)", "--pick-best-item",
    ])
    assert args.search == "Movie (2010)"
    assert args.pick_best_item is True


def test_search_item_query():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--media-item", "--search", "matrix",
    ])
    assert args.media_item is True
    assert args.search == "matrix"
    assert args.id is None
    assert args.count == 30


def test_search_library_all():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--library", "--all",
    ])
    assert args.library is True
    assert args.all is True
    assert args.id is None
    assert args.search is None


def test_search_item_all():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--media-item", "--all",
    ])
    assert args.media_item is True
    assert args.all is True


def test_search_library_id():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--library", "--id", "614156",
    ])
    assert args.library is True
    assert args.id == "614156"
    assert args.search is None


def test_search_library_query():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--library", "--search", "PELICULAS",
    ])
    assert args.library is True
    assert args.search == "PELICULAS"


def test_search_item_count():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--media-item", "--search", "matrix", "--count", "50",
    ])
    assert args.media_item is True
    assert args.search == "matrix"
    assert args.count == 50


def test_search_requires_mode():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--server", "http://x", "--api-key", "k", "search",
        ])


def test_search_modes_exclusive():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--server", "http://x", "--api-key", "k",
            "search", "--media-item", "--library", "--id", "x",
        ])


def test_version_subcommand_parses_without_server(monkeypatch):
    monkeypatch.delenv("EMBY_SERVER", raising=False)
    monkeypatch.delenv("EMBY_API_KEY", raising=False)
    monkeypatch.delenv("EMBY_USERNAME", raising=False)
    monkeypatch.delenv("EMBY_PASSWORD", raising=False)
    parser = build_parser()
    args = parser.parse_args(["version"])
    assert args.command == "version"
    assert args.server is None
