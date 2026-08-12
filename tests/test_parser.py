"""Tests for the supported argparse CLI surface."""

from __future__ import annotations

import pytest

from emby_cli.cli import build_parser


def test_build_parser_subcommands():
    subs = build_parser()._subparsers._group_actions[0].choices
    assert set(subs) == {
        "help", "login", "logout", "config", "collection", "library", "item",
        "version", "info",
    }


@pytest.mark.parametrize("command", ["search", "show", "play", "download"])
def test_removed_top_level_commands_are_rejected(command):
    with pytest.raises(SystemExit):
        build_parser().parse_args([command])


def test_help_subcommand_parses_without_server(monkeypatch):
    for name in ("EMBY_SERVER", "EMBY_API_KEY", "EMBY_USERNAME", "EMBY_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    assert build_parser().parse_args(["help"]).command == "help"


def test_parser_requires_command():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_version_subcommand_parses_without_server(monkeypatch):
    for name in ("EMBY_SERVER", "EMBY_API_KEY", "EMBY_USERNAME", "EMBY_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    args = build_parser().parse_args(["version"])
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
    args = build_parser().parse_args(["collection", "delete", "Star Wars", "--yes"])
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
        "collection", "set", "--id", "1234", "name=Peliculas", "short-name=Pelis",
    ])
    assert args.id == "1234"
    assert args.rest == ["name=Peliculas", "short-name=Pelis"]


def test_collection_create_parses_member_type():
    args = build_parser().parse_args([
        "collection", "create", "Grand Project", "--type", "audio", "--item", "1,2",
    ])
    assert args.member_type == "audio"
    assert args.name == "Grand Project"
    assert args.items == ["1,2"]


def test_collection_list_parses_order_by():
    args = build_parser().parse_args([
        "collection", "list", "--order-by", "items", "--desc", "--no-cache",
    ])
    assert args.order_by == "items"
    assert args.desc is True
    assert args.no_cache is True


def test_collection_download_parses_output_and_dry_run():
    args = build_parser().parse_args([
        "collection", "download", "Star Wars", "--output", "/tmp/out",
        "--method", "hls", "--force", "--dry-run",
    ])
    assert args.query == "Star Wars"
    assert args.output == "/tmp/out"
    assert args.method == "hls"
    assert args.force is True
    assert args.dry_run is True


def test_library_show_query_and_id_forms():
    parser = build_parser()
    by_query = parser.parse_args(["library", "show", "Movies"])
    by_id = parser.parse_args(["library", "show", "--id", "100"])
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
    assert args.lib_type == "movies"
    assert args.order_by == "items"
    assert args.desc is True


def test_item_show_query_and_id_forms():
    parser = build_parser()
    by_query = parser.parse_args(["item", "show", "Matrix"])
    by_id = parser.parse_args(["item", "show", "--id", "100"])
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
    assert args.item_type == "movie"
    assert args.year == 1999
    assert args.order_by == "year"
    assert args.desc is True
    assert args.no_cache is True


def test_item_search_parses_size_order_by():
    args = build_parser().parse_args([
        "item", "search", "--type", "movie", "--order-by", "size", "--desc",
    ])
    assert args.item_type == "movie"
    assert args.order_by == "size"
    assert args.desc is True


def test_item_play_parses_query_player_and_pick_best():
    args = build_parser().parse_args([
        "item", "play", "Matrix", "--pick-best-item", "--player", "vlc", "--wait",
    ])
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
    assert args.query == "Matrix"
    assert args.output == "/tmp/out"
    assert args.method == "stream"
    assert args.force is True
    assert args.dry_run is True


def test_item_download_from_file_parses():
    args = build_parser().parse_args([
        "item", "download", "--from-file", "titles.txt", "--dry-run",
    ])
    assert args.from_file == "titles.txt"
    assert args.dry_run is True


def test_library_download_parses_id_and_output():
    args = build_parser().parse_args([
        "library", "download", "--id", "abc", "--output", "/data",
    ])
    assert args.id == "abc"
    assert args.output == "/data"


def test_library_play_parses_player():
    args = build_parser().parse_args(["library", "play", "Movies", "--player", "vlc"])
    assert args.query == "Movies"
    assert args.player == "vlc"
    assert not hasattr(args, "wait")


def test_collection_play_parses_id_and_order_by():
    args = build_parser().parse_args([
        "collection", "play", "--id", "1234", "--player", "mpv",
        "--order-by", "release-date", "--desc",
    ])
    assert args.id == "1234"
    assert args.player == "mpv"
    assert args.order_by == "release-date"
    assert args.desc is True


def test_item_download_mirror_path_flag():
    args = build_parser().parse_args(["item", "download", "Matrix", "--mirror-path"])
    assert args.mirror_path is True


def test_library_download_path_strip_parses_from_cli():
    args = build_parser().parse_args([
        "library", "download", "Movies", "--mirror-path", "--path-strip", "/mnt/media",
    ])
    assert args.path_strip == "/mnt/media"
