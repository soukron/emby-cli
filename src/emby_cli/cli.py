"""Argument parser and entrypoint for emby-cli."""

from __future__ import annotations

import argparse
import os
import sys
import warnings

# macOS system Python ships LibreSSL; urllib3 v2 only warns, TLS still works.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import requests

from emby_cli.client import EmbyClient
from emby_cli.commands.download import cmd_download, validate_download_args
from emby_cli.commands.help import COMMAND_SUMMARIES, cmd_help
from emby_cli.commands.info import cmd_info
from emby_cli.commands.login import cmd_login
from emby_cli.commands.play import cmd_play, validate_play_args
from emby_cli.commands.search import cmd_search, validate_search_args
from emby_cli.commands.version import cmd_version
from emby_cli.constants import DEFAULT_OUTPUT, SEARCH_COUNT_DEFAULT
from emby_cli.credentials import (
    CredentialError,
    resolve_operational_auth,
    resolve_server,
)


_FORCE_HELP = "Re-download even if local file already matches"


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

    dl = sub.add_parser(
        "download",
        help=_help_by_name["download"],
    )
    mode = dl.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--media-item",
        action="store_true",
        help="Download media items; use with --id or --search",
    )
    mode.add_argument(
        "--library",
        action="store_true",
        help="Download a library; use with --id or --search",
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
        help="Search query for media item or library",
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

    sr = sub.add_parser("search", help=_help_by_name["search"])
    sr_mode = sr.add_mutually_exclusive_group(required=True)
    sr_mode.add_argument(
        "--media-item",
        action="store_true",
        help="Search media items; use with --id, --search, or --all",
    )
    sr_mode.add_argument(
        "--library",
        action="store_true",
        help="Search libraries; use with --id, --search, or --all",
    )
    sr.add_argument(
        "--id",
        default=None,
        help="Media item or library ID",
    )
    sr.add_argument(
        "--search",
        help="Search query for media item or library",
    )
    sr.add_argument(
        "--all",
        action="store_true",
        help="List all media items or libraries",
    )
    sr.add_argument(
        "--count",
        "-n",
        type=int,
        default=SEARCH_COUNT_DEFAULT,
        metavar="N",
        help=f"Max media item results (default: {SEARCH_COUNT_DEFAULT})",
    )

    pl = sub.add_parser("play", help=_help_by_name["play"])
    pl.add_argument(
        "--id",
        default=None,
        help="Media item ID to play",
    )
    pl.add_argument(
        "--search",
        help="Title line: 'Movie (2010)' or 'Show (2000) S01E01'. Allows partial matches.",
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

    sub.add_parser("version", help=_help_by_name["version"])
    sub.add_parser("info", help=_help_by_name["info"])

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
    except requests.HTTPError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        sys.exit(1)
    return client


def _validate_command_args(command: str, args: argparse.Namespace) -> str | None:
    if command == "search":
        return validate_search_args(args)
    if command == "download":
        return validate_download_args(args)
    if command == "play":
        return validate_play_args(args)
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

    if args.command == "version":
        cmd_version(args)
        return

    if args.command == "info":
        cmd_info(args)
        return

    err = _validate_command_args(args.command, args)
    if err:
        if err.startswith("error:"):
            print(err, file=sys.stderr)
        else:
            print(err)
        sys.exit(1)

    client = _open_client(args)
    commands = {
        "download": cmd_download,
        "search": cmd_search,
        "play": cmd_play,
    }
    commands[args.command](client, args)


if __name__ == "__main__":
    main()
