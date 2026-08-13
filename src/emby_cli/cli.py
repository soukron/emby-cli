"""Argument parser and entrypoint for emby-cli."""

from __future__ import annotations

import argparse
import os
import sys
import warnings

# macOS system Python ships LibreSSL; urllib3 v2 only warns, TLS still works.
# Also set in __init__.py / client.py — package import can load urllib3 first.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import requests

from emby_cli.client import AuthenticationError, EmbyClient
from emby_cli.commands.collection import cmd_collection, validate_collection_args
from emby_cli.commands.config import cmd_config
from emby_cli.commands.download import cmd_download, validate_download_args
from emby_cli.commands.help import COMMAND_SUMMARIES, cmd_help
from emby_cli.commands.info import cmd_info
from emby_cli.commands.item import cmd_item, validate_item_args
from emby_cli.commands.library import cmd_library, validate_library_args
from emby_cli.commands.login import cmd_login
from emby_cli.commands.logout import cmd_logout
from emby_cli.commands.play import cmd_play, validate_play_args
from emby_cli.commands.search import cmd_search, validate_search_args
from emby_cli.commands.show import cmd_show, validate_show_args
from emby_cli.commands.version import cmd_version
from emby_cli.constants import DEFAULT_OUTPUT, MEDIA_ITEM_ORDER_BY, SEARCH_COUNT_DEFAULT
from emby_cli.credentials import (
    CredentialError,
    resolve_operational_auth,
    resolve_server,
)

_FORCE_HELP = "Re-download even if local file already matches"


def _uses_data_cache(command: str, args: argparse.Namespace) -> bool:
    if command == "download":
        return False
    subcommand = getattr(args, "item_command", None) or getattr(args, "library_command", None)
    if command == "item" and subcommand == "download":
        return False
    if command == "library" and subcommand == "download":
        return False
    if command == "collection" and subcommand == "download":
        return False
    return True


def _add_download_options(
    parser: argparse.ArgumentParser,
    *,
    env,
    default_output: str,
    force_help: str,
) -> None:
    parser.add_argument(
        "--output",
        "-o",
        default=env("EMBY_OUTPUT", default_output),
        help=f"Output directory (env: EMBY_OUTPUT, default: {default_output})",
    )
    parser.add_argument("--force", "-f", action="store_true", help=force_help)
    parser.add_argument(
        "--throttle",
        "-t",
        type=float,
        nargs="?",
        const=1.0,
        default=0,
        help="Limit speed to playback rate (optional multiplier; default: off)",
    )
    parser.add_argument(
        "--method",
        "-m",
        default=env("EMBY_METHOD", "download"),
        choices=["download", "stream", "hls"],
        help="download, stream, or hls (env: EMBY_METHOD)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Resolve only; do not download",
    )
    parser.add_argument(
        "--mirror-path",
        action="store_true",
        help="Recreate source directory structure under the output folder",
    )
    parser.add_argument(
        "--path-strip",
        default=env("EMBY_PATH_STRIP"),
        help="With --mirror-path, strip this server path prefix (env: EMBY_PATH_STRIP)",
    )


def _add_play_options(
    parser: argparse.ArgumentParser,
    *,
    env,
    implicit_wait: bool = False,
) -> None:
    parser.add_argument(
        "--player",
        default=env("EMBY_PLAYER"),
        help="External player command or path (env: EMBY_PLAYER), e.g. vlc or "
             "/Applications/VLC.app/Contents/MacOS/VLC",
    )
    if not implicit_wait:
        parser.add_argument(
            "--wait",
            action="store_true",
            help="Block until the player process exits (default: detach and return)",
        )


def _add_item_order_by_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--order-by",
        choices=MEDIA_ITEM_ORDER_BY,
        default=None,
        help="Sort playable items before play (server-side except id)",
    )
    parser.add_argument(
        "--desc",
        action="store_true",
        help="Sort descending (default: ascending for play lists)",
    )


def build_parser() -> argparse.ArgumentParser:
    env = os.environ.get

    p = argparse.ArgumentParser(
        prog="emby-cli",
        description="Download / backup original media files from an Emby server via its REST API.",
    )
    p.add_argument("--server", "-s", default=env("EMBY_SERVER"), help="Emby server URL (env: EMBY_SERVER)")
    p.add_argument("--api-key", "-k", default=env("EMBY_API_KEY"), help="API key (env: EMBY_API_KEY)")
    p.add_argument("--username", "-u", default=env("EMBY_USERNAME"), help="Username (env: EMBY_USERNAME)")
    p.add_argument("--password", "-p", default=env("EMBY_PASSWORD"), help="Password (env: EMBY_PASSWORD)")

    sub = p.add_subparsers(dest="command", required=True)
    _help_by_name = dict(COMMAND_SUMMARIES)

    sub.add_parser("help", help=_help_by_name["help"])
    sub.add_parser("login", help=_help_by_name["login"])
    sub.add_parser("logout", help=_help_by_name["logout"])

    cfg = sub.add_parser("config", help=_help_by_name["config"])
    cfg_sub = cfg.add_subparsers(dest="config_command", required=True)
    cfg_sub.add_parser(
        "current-server",
        help="Display the current server",
    )
    cfg_sub.add_parser(
        "get-servers",
        help="Describe one or many saved servers",
    )
    use_srv = cfg_sub.add_parser(
        "use-server",
        help="Set the current server in the credentials file",
    )
    use_srv.add_argument(
        "server_name",
        metavar="NAME",
        help="Server entry name (user@url) or unique server URL",
    )
    cfg_sub.add_parser(
        "view",
        help="Display credentials file (tokens redacted)",
    )

    col = sub.add_parser("collection", help=_help_by_name["collection"])
    col.add_argument(
        "--id",
        dest="collection_id",
        help="Collection ID or unique ID prefix (may appear before the subcommand)",
    )
    col_sub = col.add_subparsers(dest="collection_command", required=True)

    col_search = col_sub.add_parser("search", help="Search collections")
    col_search.add_argument("query", nargs="?", metavar="QUERY")
    col_search.add_argument(
        "--count",
        "-n",
        default=str(SEARCH_COUNT_DEFAULT),
        metavar="N|all",
        help=f"Max results (default: {SEARCH_COUNT_DEFAULT}); use 'all' for every result",
    )
    col_search.add_argument(
        "--order-by",
        choices=["name", "id", "items", "year"],
        default=None,
    )
    col_search.add_argument("--desc", action="store_true")
    col_search.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    col_list = col_sub.add_parser(
        "list",
        help="List all collections (alias for search --count all)",
    )
    col_list.add_argument(
        "--order-by",
        choices=["name", "id", "items", "year"],
        default=None,
    )
    col_list.add_argument("--desc", action="store_true")
    col_list.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    col_show = col_sub.add_parser("show", help="Show a collection and its members")
    col_show.add_argument("query", nargs="?", metavar="QUERY")
    col_show.add_argument("--id", help="Collection ID or unique ID prefix")
    col_show.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    col_download = col_sub.add_parser(
        "download",
        help="Download all downloadable items in a collection",
    )
    col_download.add_argument("query", nargs="?", metavar="QUERY")
    col_download.add_argument("--id", help="Collection ID or unique ID prefix")
    _add_download_options(
        col_download,
        env=env,
        default_output=DEFAULT_OUTPUT,
        force_help=_FORCE_HELP,
    )

    col_play = col_sub.add_parser(
        "play",
        help="Play all playable items in a collection",
    )
    col_play.add_argument("query", nargs="?", metavar="QUERY")
    col_play.add_argument("--id", help="Collection ID or unique ID prefix")
    _add_play_options(col_play, env=env, implicit_wait=True)
    _add_item_order_by_options(col_play)

    col_create = col_sub.add_parser("create", help="Create a collection")
    col_create.add_argument("name", metavar="NAME")
    col_create.add_argument(
        "--type",
        dest="member_type",
        metavar="TYPE",
        help="Expected member item type (movie, audio/music, episode/tv, video; default: movie)",
    )
    col_create.add_argument(
        "--item",
        dest="items",
        action="append",
        default=[],
        metavar="ID[,ID...]",
        help="Initial member ID(s); repeatable and CSV-aware",
    )

    col_delete = col_sub.add_parser("delete", help="Delete a collection")
    col_delete.add_argument("query", nargs="?", metavar="QUERY")
    col_delete.add_argument("--id", help="Collection ID or unique ID prefix")
    col_delete.add_argument(
        "--yes",
        action="store_true",
        help="Delete without interactive confirmation",
    )

    col_rename = col_sub.add_parser("rename", help="Rename a collection")
    col_rename.add_argument("query", nargs="?", metavar="QUERY")
    col_rename.add_argument("new_name", metavar="NEW_NAME")
    col_rename.add_argument("--id", help="Collection ID or unique ID prefix")
    col_rename.add_argument(
        "--short-name",
        help="Also update Emby's SortName field",
    )

    col_set = col_sub.add_parser("set", help="Set collection metadata fields")
    col_set.add_argument("--id", help="Collection ID or unique ID prefix")
    col_set.add_argument(
        "rest",
        nargs="+",
        metavar="[QUERY] KEY=VALUE ...",
        help="Optional collection QUERY, then one or more KEY=VALUE assignments",
    )

    for name, summary in (
        ("add-item", "Add items to a collection"),
        ("remove-item", "Remove items from a collection"),
    ):
        member_parser = col_sub.add_parser(name, help=summary)
        member_parser.add_argument("query", nargs="?", metavar="QUERY")
        member_parser.add_argument("--id", help="Collection ID or unique ID prefix")
        member_parser.add_argument(
            "--item",
            dest="items",
            action="append",
            required=True,
            metavar="ID[,ID...]",
            help="Member ID(s); repeatable and CSV-aware",
        )

    lib = sub.add_parser("library", help=_help_by_name["library"])
    lib.add_argument(
        "--id",
        dest="library_id",
        help="Library ID or unique ID prefix (may appear before the subcommand)",
    )
    lib_sub = lib.add_subparsers(dest="library_command", required=True)

    lib_search = lib_sub.add_parser("search", help="Search libraries")
    lib_search.add_argument("query", nargs="?", metavar="QUERY")
    lib_search.add_argument(
        "--count",
        "-n",
        default=str(SEARCH_COUNT_DEFAULT),
        metavar="N|all",
        help=f"Max results (default: {SEARCH_COUNT_DEFAULT}); use 'all' for every result",
    )
    lib_search.add_argument(
        "--type",
        dest="lib_type",
        metavar="TYPE",
        help="Filter by library collection type (e.g. movies, tvshows, music)",
    )
    lib_search.add_argument(
        "--order-by",
        choices=["name", "id", "items"],
        default=None,
    )
    lib_search.add_argument("--desc", action="store_true")
    lib_search.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    lib_list = lib_sub.add_parser(
        "list",
        help="List all libraries (alias for search --count all)",
    )
    lib_list.add_argument(
        "--type",
        dest="lib_type",
        metavar="TYPE",
        help="Filter by library collection type (e.g. movies, tvshows, music)",
    )
    lib_list.add_argument(
        "--order-by",
        choices=["name", "id", "items"],
        default=None,
    )
    lib_list.add_argument("--desc", action="store_true")
    lib_list.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    lib_show = lib_sub.add_parser("show", help="Show a library and recent items")
    lib_show.add_argument("query", nargs="?", metavar="QUERY")
    lib_show.add_argument("--id", help="Library ID or unique ID prefix")
    lib_show.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    lib_download = lib_sub.add_parser(
        "download",
        help="Download all downloadable items in a library",
    )
    lib_download.add_argument("query", nargs="?", metavar="QUERY")
    lib_download.add_argument("--id", help="Library ID or unique ID prefix")
    _add_download_options(
        lib_download,
        env=env,
        default_output=DEFAULT_OUTPUT,
        force_help=_FORCE_HELP,
    )

    lib_play = lib_sub.add_parser(
        "play",
        help="Play all playable items in a library",
    )
    lib_play.add_argument("query", nargs="?", metavar="QUERY")
    lib_play.add_argument("--id", help="Library ID or unique ID prefix")
    _add_play_options(lib_play, env=env, implicit_wait=True)
    _add_item_order_by_options(lib_play)

    it = sub.add_parser("item", help=_help_by_name["item"])
    it.add_argument(
        "--id",
        dest="item_id",
        help="Media item ID or unique ID prefix (may appear before the subcommand)",
    )
    it_sub = it.add_subparsers(dest="item_command", required=True)

    it_search = it_sub.add_parser("search", help="Search media items")
    it_search.add_argument("query", nargs="?", metavar="QUERY")
    it_search.add_argument(
        "--count",
        "-n",
        default=str(SEARCH_COUNT_DEFAULT),
        metavar="N|all",
        help=f"Max results (default: {SEARCH_COUNT_DEFAULT}); use 'all' for every result",
    )
    it_search.add_argument(
        "--type",
        dest="item_type",
        metavar="TYPE",
        help="Filter by item type (e.g. movie, episode, audio, video)",
    )
    it_search.add_argument(
        "--year",
        type=int,
        metavar="YYYY",
        help="Filter by production year",
    )
    it_search.add_argument(
        "--order-by",
        choices=MEDIA_ITEM_ORDER_BY,
        default=None,
    )
    it_search.add_argument("--desc", action="store_true")
    it_search.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    it_list = it_sub.add_parser(
        "list",
        help="List all media items (alias for search --count all)",
    )
    it_list.add_argument(
        "--type",
        dest="item_type",
        metavar="TYPE",
        help="Filter by item type (e.g. movie, episode, audio, video)",
    )
    it_list.add_argument(
        "--year",
        type=int,
        metavar="YYYY",
        help="Filter by production year",
    )
    it_list.add_argument(
        "--order-by",
        choices=MEDIA_ITEM_ORDER_BY,
        default=None,
    )
    it_list.add_argument("--desc", action="store_true")
    it_list.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    it_show = it_sub.add_parser("show", help="Show a media item")
    it_show.add_argument("query", nargs="?", metavar="QUERY")
    it_show.add_argument("--id", help="Media item ID or unique ID prefix")
    it_show.add_argument(
        "--type",
        dest="item_type",
        metavar="TYPE",
        help="Require a specific item type when resolving QUERY/--id",
    )
    it_show.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    it_play = it_sub.add_parser("play", help="Play a media item in an external player")
    it_play.add_argument("query", nargs="?", metavar="QUERY")
    it_play.add_argument("--id", help="Media item ID to play (comma-separated for multiple)")
    it_play.add_argument(
        "--type",
        dest="item_type",
        metavar="TYPE",
        help="Require a specific item type when resolving QUERY/--id",
    )
    it_play.add_argument(
        "--player",
        default=env("EMBY_PLAYER"),
        help="External player command or path (env: EMBY_PLAYER), e.g. vlc or "
             "/Applications/VLC.app/Contents/MacOS/VLC",
    )
    it_play.add_argument(
        "--wait",
        action="store_true",
        help="Block until the player process exits (default: detach and return)",
    )
    it_play.add_argument(
        "--pick-best-item",
        action="store_true",
        help="On ambiguous search results, auto-select best ≤1080p "
             "(default: list matches and fail)",
    )
    it_play.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    it_download = it_sub.add_parser("download", help="Download media items")
    it_download.add_argument("query", nargs="?", metavar="QUERY")
    it_download.add_argument("--id", help="Media item ID to download (comma-separated for multiple)")
    it_download.add_argument(
        "--type",
        dest="item_type",
        metavar="TYPE",
        help="Require a specific item type when resolving QUERY/--id",
    )
    it_download.add_argument(
        "--pick-best-item",
        action="store_true",
        help="On ambiguous search results, auto-select best ≤1080p "
             "(default: list matches and fail)",
    )
    it_download.add_argument(
        "--from-file",
        "-F",
        metavar="PATH",
        dest="from_file",
        help="Download titles from a text file (one per line)",
    )
    _add_download_options(
        it_download,
        env=env,
        default_output=DEFAULT_OUTPUT,
        force_help=_FORCE_HELP,
    )

    dl = sub.add_parser(
        "download",
        help=(
            f"{_help_by_name['download']} "
            "(authorized servers only; respect the server's terms)"
        ),
    )
    mode = dl.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--item",
        "--media-item",
        nargs="?",
        const="",
        default=None,
        metavar="QUERY",
        dest="item",
        help="Download media items; optional QUERY, or use with --id "
             "(--media-item is an alias)",
    )
    mode.add_argument(
        "--library",
        nargs="?",
        const="",
        default=None,
        metavar="QUERY",
        help="Download a library; optional QUERY, or use with --id",
    )
    mode.add_argument(
        "--from-file",
        "-F",
        metavar="PATH",
        dest="from_file",
        help="Download titles from a text file (one per line)",
    )
    dl.add_argument(
        "--id",
        default=None,
        help="Media item or library ID",
    )
    dl.add_argument(
        "--search",
        help="Search query (alternative to QUERY on --item / --library)",
    )
    dl.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Resolve only; do not download",
    )
    dl.add_argument(
        "--pick-best-item",
        action="store_true",
        help="On ambiguous search results, auto-select best ≤1080p "
             "(default: list matches and fail)",
    )
    dl.add_argument(
        "--output",
        "-o",
        default=env("EMBY_OUTPUT", DEFAULT_OUTPUT),
        help=f"Output directory (env: EMBY_OUTPUT, default: {DEFAULT_OUTPUT})",
    )
    dl.add_argument("--force", "-f", action="store_true", help=_FORCE_HELP)
    dl.add_argument(
        "--throttle",
        "-t",
        type=float,
        nargs="?",
        const=1.0,
        default=0,
        help="Limit speed to playback rate (optional multiplier; default: off)",
    )
    dl.add_argument(
        "--method",
        "-m",
        default=env("EMBY_METHOD", "download"),
        choices=["download", "stream", "hls"],
        help="download, stream, or hls (env: EMBY_METHOD)",
    )
    dl.add_argument(
        "--mirror-path",
        action="store_true",
        help="Recreate source directory structure under the output folder",
    )
    dl.add_argument(
        "--path-strip",
        default=env("EMBY_PATH_STRIP"),
        help="With --mirror-path, strip this server path prefix (env: EMBY_PATH_STRIP)",
    )

    sr = sub.add_parser("search", help=_help_by_name["search"])
    sr_mode = sr.add_mutually_exclusive_group(required=True)
    sr_mode.add_argument(
        "--item",
        "--media-item",
        nargs="?",
        const="",
        default=None,
        metavar="QUERY",
        dest="item",
        help="Search media items; optional QUERY, or use with --id "
             "(--media-item is an alias)",
    )
    sr_mode.add_argument(
        "--library",
        nargs="?",
        const="",
        default=None,
        metavar="QUERY",
        help="Search libraries; optional QUERY, or use with --id",
    )
    sr.add_argument(
        "--id",
        default=None,
        help="Media item or library ID",
    )
    sr.add_argument(
        "--search",
        help="Search query (alternative to QUERY on --item / --library)",
    )
    sr.add_argument(
        "--count",
        "-n",
        default=str(SEARCH_COUNT_DEFAULT),
        metavar="N|all",
        help=(
            f"Max media item results (default: {SEARCH_COUNT_DEFAULT}); "
            "use 'all' to list everything"
        ),
    )
    sr.add_argument(
        "--type",
        dest="item_type",
        metavar="TYPE",
        help="Filter media items by type (e.g. Movie, Episode, Audio, Video)",
    )
    sr.add_argument(
        "--year",
        type=int,
        metavar="YYYY",
        help="Filter media items by production year",
    )
    sr.add_argument(
        "--order-by",
        dest="order_by",
        choices=["year", "name", "id", "size", "resolution", "items", "release-date", "added"],
        default=None,
        help="Order search results by year, name, id, size, resolution, or items",
    )
    sr.add_argument(
        "--desc",
        action="store_true",
        help="Sort in descending order",
    )
    sr.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    pl = sub.add_parser("play", help=_help_by_name["play"])
    pl.add_argument(
        "--item",
        nargs="?",
        const="",
        default=None,
        metavar="QUERY",
        dest="item",
        help="Media item to play; optional QUERY, or use with --id",
    )
    pl.add_argument(
        "--id",
        default=None,
        help="Media item ID to play",
    )
    pl.add_argument(
        "--search",
        help="Title line (alternative to QUERY on --item): "
             "'Movie (2010)' or 'Show (2000) S01E01'. Allows partial matches.",
    )
    pl.add_argument(
        "--player",
        default=env("EMBY_PLAYER"),
        help="External player command or path (env: EMBY_PLAYER), e.g. vlc or "
             "/Applications/VLC.app/Contents/MacOS/VLC",
    )
    pl.add_argument(
        "--wait",
        action="store_true",
        help="Block until the player process exits (default: detach and return)",
    )
    pl.add_argument(
        "--pick-best-item",
        action="store_true",
        help="On ambiguous search results, auto-select best ≤1080p "
             "(default: list matches and fail)",
    )
    pl.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    sh = sub.add_parser("show", help=_help_by_name["show"])
    sh_mode = sh.add_mutually_exclusive_group(required=True)
    sh_mode.add_argument(
        "--item",
        "--media-item",
        action="store_const",
        const=True,
        default=None,
        dest="item",
        help="Show a media item (requires --id; --media-item is an alias)",
    )
    sh_mode.add_argument(
        "--library",
        action="store_const",
        const=True,
        default=None,
        help="Show a library (requires --id)",
    )
    sh.add_argument(
        "--id",
        required=True,
        help="Media item or library ID",
    )
    sh.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    sub.add_parser("version", help=_help_by_name["version"])
    info = sub.add_parser("info", help=_help_by_name["info"])
    info.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache read and refresh it from API",
    )

    return p


def _open_client(args: argparse.Namespace) -> EmbyClient:
    """Build a client for operational commands (api key, cache, or transparent login)."""
    try:
        server = resolve_server(args, prompt=False)
    except CredentialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    api_key, username, password = resolve_operational_auth(args)
    client = EmbyClient(server, api_key=api_key)
    client.use_data_cache = _uses_data_cache(args.command, args)
    client.no_data_cache = bool(getattr(args, "no_cache", False))

    if api_key:
        return client

    try:
        client.ensure_user_session(username, password)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "Provide --api-key / EMBY_API_KEY, --username / EMBY_USERNAME, "
            "or run `emby-cli login`",
            file=sys.stderr,
        )
        sys.exit(1)
    except AuthenticationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except requests.HTTPError as exc:
        resp = getattr(exc, "response", None)
        if resp is not None and resp.status_code in (401, 403):
            print(f"error: {exc}", file=sys.stderr)
            print(
                "Run `emby-cli login` (or pass a valid --api-key) and try again.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Authentication failed: {exc}", file=sys.stderr)
        sys.exit(1)
    return client


def _validate_command_args(command: str, args: argparse.Namespace) -> str | None:
    if command == "collection":
        return validate_collection_args(args)
    if command == "library":
        return validate_library_args(args)
    if command == "item":
        return validate_item_args(args)
    if command == "search":
        return validate_search_args(args)
    if command == "download":
        return validate_download_args(args)
    if command == "play":
        return validate_play_args(args)
    if command == "show":
        return validate_show_args(args)
    return None


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "help":
        cmd_help()
        return

    if args.command == "login":
        cmd_login(args)
        return

    if args.command == "logout":
        cmd_logout(args)
        return

    if args.command == "config":
        cmd_config(args)
        return

    if args.command == "version":
        cmd_version(args)
        return

    if args.command == "info":
        cmd_info(args)
        return

    err = _validate_command_args(args.command, args)
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)

    client = _open_client(args)
    commands = {
        "collection": cmd_collection,
        "library": cmd_library,
        "item": cmd_item,
        "download": cmd_download,
        "search": cmd_search,
        "play": cmd_play,
        "show": cmd_show,
    }
    try:
        commands[args.command](client, args)
    except AuthenticationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except requests.HTTPError as exc:
        response = getattr(exc, "response", None)
        if (
            args.command == "collection"
            and response is not None
            and response.status_code == 403
        ):
            print(
                "error: collection operation requires metadata edit permissions",
                file=sys.stderr,
            )
        else:
            print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
