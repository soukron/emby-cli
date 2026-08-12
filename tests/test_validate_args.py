"""Canonical selector validation runs before authentication."""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from emby_cli.cli import main
from emby_cli.commands.collection import validate_collection_args
from emby_cli.commands.item import validate_item_args
from emby_cli.commands.library import validate_library_args
from emby_cli.item_ops import DownloadOpts


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
        items=["1,2", "3"], member_type=None,
    )) is None


def test_validate_collection_rejects_unknown_member_type():
    assert validate_collection_args(argparse.Namespace(
        collection_command="create", name="Saga", items=[], member_type="playlist",
    )) == "error: --type must be one of audio, episode, episodes, movie, movies, music, tv, video, videos"


def test_validate_collection_list_requires_no_extra_args():
    assert validate_collection_args(argparse.Namespace(collection_command="list")) is None


def test_validate_collection_set_requires_selector_and_assignments():
    assert validate_collection_args(argparse.Namespace(
        collection_command="set", query=None, id=None, collection_id=None,
        rest=["year=1980"],
    )) == "provide exactly one collection QUERY or --id"
    assert validate_collection_args(argparse.Namespace(
        collection_command="set", query=None, id="1234", collection_id=None, rest=[],
    )) == "provide at least one KEY=VALUE assignment"
    assert validate_collection_args(argparse.Namespace(
        collection_command="set", query=None, id=None, collection_id="1234",
        rest=["year=1980"],
    )) is None


def test_validate_collection_set_rejects_unknown_field():
    assert validate_collection_args(argparse.Namespace(
        collection_command="set", query=None, id="1234", collection_id=None,
        rest=["genre=Action"],
    )) == "unknown field 'genre'; allowed: display-order, name, overview, short-name, year"


def test_validate_collection_download_and_play_require_selector():
    for command in ("download", "play"):
        assert validate_collection_args(argparse.Namespace(
            collection_command=command, query=None, id=None, collection_id=None,
        )) == "provide exactly one collection QUERY or --id"


def test_download_opts_from_args_uses_defaults_and_normalizes_values():
    opts = DownloadOpts.from_args(argparse.Namespace(
        output="backup", method="stream", throttle=2, dry_run=True,
        mirror_path=False, path_strip=None,
    ))
    assert str(opts.output) == "backup"
    assert opts.method == "stream"
    assert opts.throttle == 2
    assert opts.dry_run is True


def test_download_opts_from_args_reads_mirror_path():
    opts = DownloadOpts.from_args(argparse.Namespace(
        output="backup", throttle=0, mirror_path=True,
    ))
    assert opts.mirror_path is True


def test_download_opts_from_args_reads_path_strip():
    opts = DownloadOpts.from_args(argparse.Namespace(
        output="backup", throttle=0, path_strip=" /mnt/media ",
    ))
    assert opts.path_strip == "/mnt/media"


def test_main_collection_invalid_selector_skips_auth(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["emby-cli", "collection", "show"])
    with patch("emby_cli.cli._open_client") as open_client, pytest.raises(SystemExit) as exc:
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
    with patch("emby_cli.cli._open_client") as open_client, pytest.raises(SystemExit) as exc:
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
        item_command="download", query=None, id=None, item_id=None,
        from_file=None, pick_best_item=False,
    )) == "provide exactly one media item QUERY or --id"
    assert validate_item_args(argparse.Namespace(
        item_command="download", query="Matrix", id=None, item_id=None,
        from_file="titles.txt", pick_best_item=False,
    )) == "With --from-file, do not pass QUERY or --id"
    assert validate_item_args(argparse.Namespace(
        item_command="download", query=None, id=None, item_id=None,
        from_file="titles.txt", pick_best_item=False,
    )) is None


def test_validate_library_download_and_play_require_selector():
    for command in ("download", "play"):
        assert validate_library_args(argparse.Namespace(
            library_command=command, query=None, id=None, library_id=None,
        )) == "provide exactly one library QUERY or --id"


@pytest.mark.parametrize("subcommand", ["play", "download"])
def test_main_item_ignores_removed_emby_item_id(subcommand, capsys, monkeypatch):
    monkeypatch.setenv("EMBY_ITEM_ID", "environment-id")
    monkeypatch.setattr("sys.argv", ["emby-cli", "item", subcommand])
    with patch("emby_cli.cli._open_client") as open_client, pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    open_client.assert_not_called()
    assert "exactly one media item QUERY or --id" in capsys.readouterr().err


def test_main_item_invalid_selector_skips_auth(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["emby-cli", "item", "show"])
    with patch("emby_cli.cli._open_client") as open_client, pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    open_client.assert_not_called()
    assert "exactly one media item QUERY or --id" in capsys.readouterr().err
