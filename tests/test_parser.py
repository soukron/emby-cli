"""Tests for argparse CLI surface."""

from __future__ import annotations

import pytest

from emby_cli.cli import build_parser


def test_build_parser_subcommands():
    parser = build_parser()
    subs = parser._subparsers._group_actions[0].choices
    assert set(subs) == {
        "help", "login", "logout", "config", "download", "search", "show", "play", "version", "info",
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
    assert args.item == ""
    assert args.id == "abc"
    assert args.output == "./downloads"
    assert args.method == "download"
    assert args.dry_run is False


def test_download_item_alias():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "download", "--item", "--id", "abc",
    ])
    assert args.item == ""
    assert args.id == "abc"


def test_download_item_query_embedded():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "download", "--item", "fast and furious",
    ])
    assert args.item == "fast and furious"
    assert args.search is None
    assert args.id is None


def test_download_item_search_pick_best():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "download", "--media-item", "--search", "Show S01E01", "--pick-best-item",
    ])
    assert args.item == ""
    assert args.search == "Show S01E01"
    assert args.pick_best_item is True


def test_download_library_search():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "download", "--library", "--search", "Movies",
    ])
    assert args.library == ""
    assert args.search == "Movies"


def test_download_library_query_embedded():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "download", "--library", "peliculas",
    ])
    assert args.library == "peliculas"
    assert args.search is None


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
    assert args.item is None
    assert args.search is None


def test_play_id_csv():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "play", "--id", "1,2,3",
    ])
    assert args.id == "1,2,3"


def test_play_item_query_embedded():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "play", "--item", "Movie (2010)", "--pick-best-item",
    ])
    assert args.item == "Movie (2010)"
    assert args.search is None
    assert args.pick_best_item is True


def test_play_search_pick_best():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "play", "--search", "Movie (2010)", "--pick-best-item",
    ])
    assert args.search == "Movie (2010)"
    assert args.item is None
    assert args.pick_best_item is True


def test_play_item_with_id():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "play", "--item", "--id", "abc",
    ])
    assert args.item == ""
    assert args.id == "abc"


def test_search_item_query_embedded():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--item", "fast and furious",
    ])
    assert args.item == "fast and furious"
    assert args.library is None
    assert args.search is None
    assert args.id is None
    assert args.count == "30"


def test_search_item_query_via_search_flag():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--item", "--search", "matrix",
    ])
    assert args.item == ""
    assert args.search == "matrix"
    assert args.id is None
    assert args.count == "30"


def test_search_media_item_alias():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--media-item", "matrix",
    ])
    assert args.item == "matrix"


def test_search_library_count_all():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--library", "--count", "all",
    ])
    assert args.library == ""
    assert args.count == "all"
    assert args.id is None
    assert args.search is None


def test_search_item_count_all():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--item", "--count", "all",
    ])
    assert args.item == ""
    assert args.count == "all"


def test_search_library_id():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--library", "--id", "614156",
    ])
    assert args.library == ""
    assert args.id == "614156"
    assert args.search is None


def test_search_library_query_embedded():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--library", "peliculas",
    ])
    assert args.library == "peliculas"
    assert args.search is None


def test_search_library_query_via_search_flag():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--library", "--search", "PELICULAS",
    ])
    assert args.library == ""
    assert args.search == "PELICULAS"


def test_search_item_count():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--item", "matrix", "--count", "50",
    ])
    assert args.item == "matrix"
    assert args.count == "50"


def test_search_item_type_and_year():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--item", "spider", "--type", "Movie", "--year", "2026",
    ])
    assert args.item == "spider"
    assert args.item_type == "Movie"
    assert args.year == 2026


def test_search_sort_and_desc():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--item", "spider", "--order-by", "year", "--desc",
    ])
    assert args.order_by == "year"
    assert args.desc is True


def test_search_order_by_size():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--item", "spider", "--order-by", "size",
    ])
    assert args.order_by == "size"


def test_search_order_by_name():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--item", "spider", "--order-by", "name",
    ])
    assert args.order_by == "name"


def test_search_order_by_items():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--library", "--count", "all", "--order-by", "items",
    ])
    assert args.order_by == "items"


def test_search_no_cache_flag():
    parser = build_parser()
    args = parser.parse_args([
        "--server", "http://x", "--api-key", "k",
        "search", "--library", "--count", "1", "--no-cache",
    ])
    assert args.no_cache is True


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
            "search", "--item", "--library", "--id", "x",
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
