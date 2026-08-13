"""Tests for argparse CLI surface."""

from __future__ import annotations

import pytest

from emby_cli.cli import build_parser


def test_build_parser_subcommands():
    parser = build_parser()
    subs = parser._subparsers._group_actions[0].choices
    assert set(subs) == {
        "help", "login", "logout", "config", "collection", "library", "item", "download",
        "search", "show", "play", "version", "info",
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


def test_collection_show_query_and_id_forms():
    parser = build_parser()
    by_query = parser.parse_args(["collection", "show", "Star Wars"])
    by_id = parser.parse_args(["collection", "show", "--id", "123"])
    assert by_query.query == "Star Wars"
    assert by_query.id is None
    assert by_id.query is None
    assert by_id.id == "123"


def test_collection_rename_id_and_short_name():
    args = build_parser().parse_args([
        "collection", "rename", "--id", "123", "New Name",
        "--short-name", "New 01",
    ])
    assert args.query is None
    assert args.id == "123"
    assert args.new_name == "New Name"
    assert args.short_name == "New 01"


def test_collection_items_are_repeatable_csv_values():
    args = build_parser().parse_args([
        "collection", "add-item", "--id", "123",
        "--item", "456,789", "--item", "101",
    ])
    assert args.items == ["456,789", "101"]


def test_collection_delete_yes():
    args = build_parser().parse_args([
        "collection", "delete", "Star Wars", "--yes",
    ])
    assert args.query == "Star Wars"
    assert args.yes is True


def test_collection_set_parent_id_before_subcommand():
    args = build_parser().parse_args([
        "collection", "--id", "1234", "set", "year=1980",
    ])
    assert args.collection_command == "set"
    assert args.collection_id == "1234"
    assert args.id is None
    assert args.rest == ["year=1980"]


def test_collection_set_multiple_assignments():
    args = build_parser().parse_args([
        "collection", "set", "--id", "1234",
        "name=Peliculas", "short-name=Pelis",
    ])
    assert args.id == "1234"
    assert args.rest == ["name=Peliculas", "short-name=Pelis"]


def test_collection_create_parses_member_type():
    args = build_parser().parse_args([
        "collection", "create", "Grand Project", "--type", "audio", "--item", "1,2",
    ])
    assert args.member_type == "audio"
    assert args.collection_command == "create"
    assert args.name == "Grand Project"
    assert args.items == ["1,2"]


def test_collection_list_parses_order_by():
    args = build_parser().parse_args([
        "collection", "list", "--order-by", "items", "--desc", "--no-cache",
    ])
    assert args.collection_command == "list"
    assert args.order_by == "items"
    assert args.desc is True
    assert args.no_cache is True


def test_collection_download_parses_output_and_dry_run():
    args = build_parser().parse_args([
        "collection", "download", "Star Wars", "--output", "/tmp/out",
        "--method", "hls", "--force", "--dry-run",
    ])
    assert args.collection_command == "download"
    assert args.query == "Star Wars"
    assert args.output == "/tmp/out"
    assert args.method == "hls"
    assert args.force is True
    assert args.dry_run is True


def test_library_show_query_and_id_forms():
    parser = build_parser()
    by_query = parser.parse_args(["library", "show", "Movies"])
    by_id = parser.parse_args(["library", "show", "--id", "100"])
    assert by_query.library_command == "show"
    assert by_query.query == "Movies"
    assert by_id.id == "100"


def test_library_parent_id_before_show():
    args = build_parser().parse_args(["library", "--id", "100", "show"])
    assert args.library_command == "show"
    assert args.library_id == "100"


def test_library_list_parses_type_and_order_by():
    args = build_parser().parse_args([
        "library", "list", "--type", "movies", "--order-by", "items", "--desc",
    ])
    assert args.library_command == "list"
    assert args.lib_type == "movies"
    assert args.order_by == "items"
    assert args.desc is True


def test_item_show_query_and_id_forms():
    parser = build_parser()
    by_query = parser.parse_args(["item", "show", "Matrix"])
    by_id = parser.parse_args(["item", "show", "--id", "100"])
    assert by_query.item_command == "show"
    assert by_query.query == "Matrix"
    assert by_id.id == "100"


def test_item_parent_id_before_show():
    args = build_parser().parse_args(["item", "--id", "100", "show"])
    assert args.item_command == "show"
    assert args.item_id == "100"


def test_item_list_parses_type_year_and_order_by():
    args = build_parser().parse_args([
        "item", "list", "--type", "movie", "--year", "1999",
        "--order-by", "year", "--desc", "--no-cache",
    ])
    assert args.item_command == "list"
    assert args.item_type == "movie"
    assert args.year == 1999
    assert args.order_by == "year"
    assert args.desc is True
    assert args.no_cache is True


def test_item_search_parses_size_order_by():
    args = build_parser().parse_args([
        "item", "search", "--type", "movie", "--order-by", "size", "--desc",
    ])
    assert args.item_command == "search"
    assert args.item_type == "movie"
    assert args.order_by == "size"
    assert args.desc is True


def test_item_play_parses_query_player_and_pick_best():
    args = build_parser().parse_args([
        "item", "play", "Matrix", "--pick-best-item", "--player", "vlc", "--wait",
    ])
    assert args.item_command == "play"
    assert args.query == "Matrix"
    assert args.pick_best_item is True
    assert args.player == "vlc"
    assert args.wait is True


def test_item_play_parses_id_and_parent_id():
    parser = build_parser()
    by_sub = parser.parse_args(["item", "play", "--id", "100"])
    by_parent = parser.parse_args(["item", "--id", "100", "play"])
    assert by_sub.id == "100"
    assert by_parent.item_id == "100"


def test_item_download_parses_output_method_and_dry_run():
    args = build_parser().parse_args([
        "item", "download", "Matrix", "--output", "/tmp/out", "--method", "stream",
        "--force", "--dry-run",
    ])
    assert args.item_command == "download"
    assert args.query == "Matrix"
    assert args.output == "/tmp/out"
    assert args.method == "stream"
    assert args.force is True
    assert args.dry_run is True


def test_item_download_from_file_parses():
    args = build_parser().parse_args([
        "item", "download", "--from-file", "titles.txt", "--dry-run",
    ])
    assert args.item_command == "download"
    assert args.from_file == "titles.txt"
    assert args.dry_run is True


def test_library_download_parses_id_and_output():
    args = build_parser().parse_args([
        "library", "download", "--id", "abc", "--output", "/data",
    ])
    assert args.library_command == "download"
    assert args.id == "abc"
    assert args.output == "/data"


def test_library_play_parses_player():
    args = build_parser().parse_args([
        "library", "play", "Movies", "--player", "vlc",
    ])
    assert args.library_command == "play"
    assert args.query == "Movies"
    assert args.player == "vlc"
    assert not hasattr(args, "wait")


def test_collection_play_parses_id():
    args = build_parser().parse_args([
        "collection", "play", "--id", "1234", "--player", "mpv",
    ])
    assert args.collection_command == "play"
    assert args.id == "1234"
    assert args.player == "mpv"


def test_collection_play_parses_order_by():
    args = build_parser().parse_args([
        "collection", "play", "--id", "1234", "--order-by", "release-date", "--desc",
    ])
    assert args.order_by == "release-date"
    assert args.desc is True


def test_download_mirror_path_flag():
    args = build_parser().parse_args([
        "item", "download", "Matrix", "--mirror-path",
    ])
    assert args.mirror_path is True

    legacy = build_parser().parse_args([
        "download", "--item", "--id", "1", "--mirror-path",
    ])
    assert legacy.mirror_path is True


def test_download_path_strip_parses_from_cli():
    args = build_parser().parse_args([
        "library", "download", "Movies", "--mirror-path", "--path-strip", "/mnt/media",
    ])
    assert args.path_strip == "/mnt/media"
