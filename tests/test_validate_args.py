"""Selector validation runs before authentication."""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from emby_cli.cli import main
from emby_cli.commands.collection import validate_collection_args
from emby_cli.commands.download import validate_download_args
from emby_cli.commands.item import validate_item_args
from emby_cli.commands.library import validate_library_args
from emby_cli.commands.play import validate_play_args
from emby_cli.commands.search import validate_search_args
from emby_cli.item_ops import DownloadOpts
from emby_cli.mode_args import resolve_item_id


def test_validate_search_item_requires_selector_without_count_all():
    args = argparse.Namespace(
        library=None,
        item="",
        id=None,
        search=None,
        count=30,
    )
    assert validate_search_args(args) == (
        "Provide QUERY/--search or --id. "
        "Use --count all to list everything."
    )


def test_validate_collection_requires_exactly_one_selector():
    assert validate_collection_args(argparse.Namespace(
        collection_command="show", query=None, id=None,
    )) == "provide exactly one collection QUERY or --id"
    assert validate_collection_args(argparse.Namespace(
        collection_command="show", query="Saga", id="1",
    )) == "provide exactly one collection QUERY or --id"


def test_validate_collection_rejects_empty_csv_member_before_auth():
    assert validate_collection_args(argparse.Namespace(
        collection_command="add-item", query=None, id="1", items=["2,,3"],
    )) == "--item contains an empty ID"


def test_validate_collection_accepts_repeated_csv_members():
    assert validate_collection_args(argparse.Namespace(
        collection_command="remove-item", query="Saga", id=None,
        items=["1,2", "3"],
    )) is None


def test_validate_collection_list_requires_no_extra_args():
    assert validate_collection_args(argparse.Namespace(
        collection_command="list",
    )) is None


def test_validate_collection_set_requires_selector_and_assignments():
    assert validate_collection_args(argparse.Namespace(
        collection_command="set", query=None, id=None, collection_id=None,
        rest=["year=1980"],
    )) == "provide exactly one collection QUERY or --id"
    assert validate_collection_args(argparse.Namespace(
        collection_command="set", query=None, id="1234", collection_id=None,
        rest=[],
    )) == "provide at least one KEY=VALUE assignment"
    assert validate_collection_args(argparse.Namespace(
        collection_command="set", query=None, id=None, collection_id="1234",
        rest=["year=1980"],
    )) is None
    assert validate_collection_args(argparse.Namespace(
        collection_command="set", query=None, id=None, collection_id=None,
        rest=["Star Wars", "year=1980"],
    )) is None


def test_validate_collection_download_requires_selector():
    assert validate_collection_args(argparse.Namespace(
        collection_command="download", query=None, id=None, collection_id=None,
    )) == "provide exactly one collection QUERY or --id"


def test_validate_collection_play_requires_selector():
    assert validate_collection_args(argparse.Namespace(
        collection_command="play", query=None, id=None, collection_id=None,
    )) == "provide exactly one collection QUERY or --id"


def test_validate_collection_set_rejects_unknown_field():
    assert validate_collection_args(argparse.Namespace(
        collection_command="set", query=None, id="1234", collection_id=None,
        rest=["genre=Action"],
    )) == "unknown field 'genre'; allowed: display-order, name, overview, short-name, year"


def test_validate_search_library_allows_empty_selector_with_count_n():
    args = argparse.Namespace(
        library="",
        item=None,
        id=None,
        search=None,
        count=1,
    )
    assert validate_search_args(args) is None


def test_validate_search_ok_embedded_query():
    args = argparse.Namespace(
        library="peliculas",
        item=None,
        id=None,
        search=None,
        all=False,
        count=30,
    )
    assert validate_search_args(args) is None


def test_validate_search_ok_count_all():
    args = argparse.Namespace(
        library="",
        item=None,
        id=None,
        search=None,
        count="all",
    )
    assert validate_search_args(args) is None


def test_validate_search_rejects_embedded_and_search_flag():
    args = argparse.Namespace(
        item="matrix",
        library=None,
        id=None,
        search="other",
        count=30,
    )
    assert validate_search_args(args) == (
        "Do not pass --search when QUERY is given to --item / --library"
    )


def test_validate_search_count_positive():
    args = argparse.Namespace(
        library=None,
        item="x",
        id=None,
        search=None,
        count=0,
    )
    assert validate_search_args(args) == "error: --count must be >= 1"


def test_validate_search_year_only_with_items():
    args = argparse.Namespace(
        library="",
        item=None,
        id=None,
        search=None,
        count="all",
        item_type="Movie",
        year=2026,
    )
    assert validate_search_args(args) == "--year can only be used with --item/--media-item"


def test_validate_search_rejects_id_with_filters():
    args = argparse.Namespace(
        library=None,
        item="",
        id="123",
        search=None,
        count=30,
        item_type="Movie",
        year=2026,
    )
    assert validate_search_args(args) == "--type/--year cannot be used with --id"


def test_validate_search_rejects_unknown_type():
    args = argparse.Namespace(
        library=None,
        item="matrix",
        id=None,
        search=None,
        count=30,
        item_type="Documentary",
        year=None,
    )
    assert validate_search_args(args) == "error: --type must be one of Movie, Episode, Audio, Video"


def test_validate_search_accepts_lowercase_type():
    args = argparse.Namespace(
        library=None,
        item="spider-man",
        id=None,
        search=None,
        count="all",
        item_type="movie",
        year=2026,
    )
    assert validate_search_args(args) is None


def test_validate_search_rejects_library_sort_year():
    args = argparse.Namespace(
        library="movies",
        item=None,
        id=None,
        search=None,
        count=30,
        order_by="year",
        item_type=None,
        year=None,
    )
    assert validate_search_args(args) == (
        "--order-by year/size/resolution/release-date/added can only be used with --item/--media-item"
    )


def test_validate_search_rejects_library_sort_size():
    args = argparse.Namespace(
        library="movies",
        item=None,
        id=None,
        search=None,
        count=30,
        order_by="size",
        item_type=None,
        year=None,
    )
    assert validate_search_args(args) == (
        "--order-by year/size/resolution/release-date/added can only be used with --item/--media-item"
    )


def test_validate_search_accepts_library_type_filter():
    args = argparse.Namespace(
        library="",
        item=None,
        id=None,
        search=None,
        count="all",
        order_by="items",
        item_type="tvshows",
        year=None,
    )
    assert validate_search_args(args) is None


def test_validate_search_rejects_item_order_by_items():
    args = argparse.Namespace(
        library=None,
        item="matrix",
        id=None,
        search=None,
        count=30,
        order_by="items",
        item_type=None,
        year=None,
    )
    assert validate_search_args(args) == "--order-by items can only be used with --library"


def test_validate_download_media_item_needs_selector(monkeypatch):
    monkeypatch.delenv("EMBY_ITEM_ID", raising=False)
    args = argparse.Namespace(
        item="",
        library=None,
        from_file=None,
        id=None,
        search=None,
        pick_best_item=False,
    )
    assert validate_download_args(args) == (
        "With --item, provide exactly one of --id or QUERY/--search"
    )


def test_download_opts_from_args_uses_defaults_and_normalizes_values():
    opts = DownloadOpts.from_args(argparse.Namespace(output="backup", throttle=None))

    assert str(opts.output) == "backup"
    assert opts.throttle == 0
    assert opts.method == "download"
    assert opts.dry_run is False
    assert opts.mirror_path is False


def test_download_opts_from_args_reads_mirror_path():
    opts = DownloadOpts.from_args(
        argparse.Namespace(output="backup", throttle=0, mirror_path=True)
    )
    assert opts.mirror_path is True


def test_download_opts_from_args_reads_path_strip():
    opts = DownloadOpts.from_args(
        argparse.Namespace(
            output="backup",
            throttle=0,
            path_strip=" /mnt/media ",
        )
    )
    assert opts.path_strip == "/mnt/media"


def test_resolve_item_id_prefers_flag_over_environment(monkeypatch):
    monkeypatch.setenv("EMBY_ITEM_ID", "environment-id")

    assert resolve_item_id(argparse.Namespace(id="  flag-id  ")) == "flag-id"
    assert resolve_item_id(argparse.Namespace(id=None)) == "environment-id"
    assert resolve_item_id(argparse.Namespace(id=None), include_env=False) is None


def test_validate_download_item_embedded_ok():
    args = argparse.Namespace(
        item="matrix",
        library=None,
        from_file=None,
        id=None,
        search=None,
        pick_best_item=False,
    )
    assert validate_download_args(args) is None


def test_validate_download_library_rejects_pick_best():
    args = argparse.Namespace(
        item=None,
        library="Movies",
        from_file=None,
        id=None,
        search=None,
        pick_best_item=True,
    )
    assert validate_download_args(args) == (
        "--pick-best-item cannot be used with --library"
    )


def test_validate_download_from_file_rejects_id():
    args = argparse.Namespace(
        item=None,
        library=None,
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
    args = argparse.Namespace(
        id=None, item=None, search=None, pick_best_item=False,
    )
    assert validate_play_args(args) == (
        "Provide exactly one of --id or QUERY/--search"
    )


def test_validate_play_item_query_ok():
    args = argparse.Namespace(
        id=None, item="Movie (2010)", search=None, pick_best_item=True,
    )
    assert validate_play_args(args) is None


def test_validate_play_pick_best_only_with_query():
    args = argparse.Namespace(
        id="1", item=None, search=None, pick_best_item=True,
    )
    assert validate_play_args(args) == (
        "--pick-best-item can only be used with QUERY/--search"
    )


def test_validate_play_item_and_search_conflict():
    args = argparse.Namespace(
        id=None, item="a", search="b", pick_best_item=False,
    )
    assert validate_play_args(args) == (
        "Do not pass --search when QUERY is given to --item / --library"
    )


def test_main_search_library_without_selector_skips_auth(capsys, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["emby-cli", "--server", "http://x", "--api-key", "k", "search", "--library"],
    )
    with (
        patch("emby_cli.cli._open_client") as open_client,
        patch("emby_cli.cli.cmd_search") as cmd_search,
    ):
        main()
    open_client.assert_called_once()
    cmd_search.assert_called_once()
    assert "No results." not in capsys.readouterr().err


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
    assert "With --library, provide exactly one of --id or QUERY/--search" in (
        capsys.readouterr().err
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
    assert "Provide exactly one of --id or QUERY/--search" in (
        capsys.readouterr().err
    )


def test_main_collection_invalid_selector_skips_auth(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["emby-cli", "collection", "show"])
    with patch("emby_cli.cli._open_client") as open_client:
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    open_client.assert_not_called()
    assert "exactly one collection QUERY or --id" in capsys.readouterr().err


def test_validate_library_requires_exactly_one_selector_for_show():
    assert validate_library_args(argparse.Namespace(
        library_command="show", query=None, id=None, library_id=None,
    )) == "provide exactly one library QUERY or --id"
    assert validate_library_args(argparse.Namespace(
        library_command="show", query="Movies", id="1", library_id=None,
    )) == "provide exactly one library QUERY or --id"


def test_validate_library_list_accepts_type_filter():
    assert validate_library_args(argparse.Namespace(
        library_command="list", lib_type="movies",
    )) is None
    assert validate_library_args(argparse.Namespace(
        library_command="search", query="", count="all", lib_type="bad",
    )) == "error: --type must be one of book, books, homevideo, homevideos, mixed, movie, movies, music, photo, photos, tv, tvshow, tvshows"


def test_main_library_invalid_selector_skips_auth(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["emby-cli", "library", "show"])
    with patch("emby_cli.cli._open_client") as open_client:
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    open_client.assert_not_called()
    assert "exactly one library QUERY or --id" in capsys.readouterr().err


def test_validate_item_requires_exactly_one_selector_for_show():
    assert validate_item_args(argparse.Namespace(
        item_command="show", query=None, id=None, item_id=None,
    )) == "provide exactly one media item QUERY or --id"
    assert validate_item_args(argparse.Namespace(
        item_command="show", query="Matrix", id="1", item_id=None,
    )) == "provide exactly one media item QUERY or --id"


def test_validate_item_play_requires_selector_and_pick_best_rules():
    assert validate_item_args(argparse.Namespace(
        item_command="play", query=None, id=None, item_id=None, pick_best_item=False,
    )) == "provide exactly one media item QUERY or --id"
    assert validate_item_args(argparse.Namespace(
        item_command="play", query="Matrix", id=None, item_id=None, pick_best_item=True,
    )) is None
    assert validate_item_args(argparse.Namespace(
        item_command="play", query=None, id="1", item_id=None, pick_best_item=True,
    )) == "--pick-best-item can only be used with QUERY"


def test_validate_item_download_requires_selector():
    assert validate_item_args(argparse.Namespace(
        item_command="download", query=None, id=None, item_id=None, pick_best_item=False,
    )) == "provide exactly one media item QUERY or --id"


def test_validate_library_download_requires_selector():
    assert validate_library_args(argparse.Namespace(
        library_command="download", query=None, id=None, library_id=None,
    )) == "provide exactly one library QUERY or --id"


def test_validate_library_play_requires_selector():
    assert validate_library_args(argparse.Namespace(
        library_command="play", query=None, id=None, library_id=None,
    )) == "provide exactly one library QUERY or --id"


def test_main_item_invalid_selector_skips_auth(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["emby-cli", "item", "show"])
    with patch("emby_cli.cli._open_client") as open_client:
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    open_client.assert_not_called()
    assert "exactly one media item QUERY or --id" in capsys.readouterr().err
