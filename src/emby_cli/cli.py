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
from emby_cli.commands.batch import cmd_batch
from emby_cli.commands.download import cmd_download
from emby_cli.commands.list import cmd_list
from emby_cli.commands.play import cmd_play
from emby_cli.commands.search import cmd_search
from emby_cli.commands.sync import cmd_sync
from emby_cli.constants import DEFAULT_OUTPUT


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

    ls = sub.add_parser("list", help="List libraries or items in a library")
    ls.add_argument("--library", "-l", help="Library name to list items for")

    dl = sub.add_parser("download", help="Download items")
    dl.add_argument("--library", "-l", help="Library name to download")
    dl.add_argument("--item-id", "-i", default=env("EMBY_ITEM_ID"), help="Specific item ID to download (env: EMBY_ITEM_ID)")
    dl.add_argument("--output", "-o", default=env("EMBY_OUTPUT", DEFAULT_OUTPUT),
                    help=f"Output directory (env: EMBY_OUTPUT, default: {DEFAULT_OUTPUT})")
    dl.add_argument("--force", "-f", action="store_true", help="Re-download even if file exists with matching size")
    dl.add_argument("--throttle", "-t", type=float, nargs="?", const=1.0, default=0,
                    help="Limit speed to playback rate. Optional multiplier: 1=realtime, 1.5=50%% faster (default: off)")
    dl.add_argument("--method", "-m", default=env("EMBY_METHOD", "download"),
                    choices=["download", "stream", "hls"],
                    help="Download method: 'download' (API Download), 'stream' (browser-like original.*), "
                         "or 'hls' (stream chunks + remux) (env: EMBY_METHOD)")

    sr = sub.add_parser("search", help="Search for items by name")
    sr.add_argument("query", help="Search query")

    pl = sub.add_parser("play", help="Play an item via DirectStreamUrl in an external player")
    pl.add_argument("query", nargs="?",
                    help="Title line like batch: 'Movie (2010)' or 'Show (2000) S01E01'")
    pl.add_argument("--item-id", "-i", default=env("EMBY_ITEM_ID"),
                    help="Item ID to play (env: EMBY_ITEM_ID)")
    pl.add_argument("--player", default=env("EMBY_PLAYER"),
                    help="External player command or path (env: EMBY_PLAYER), e.g. vlc or "
                         "/Applications/VLC.app/Contents/MacOS/VLC")
    pl.add_argument("--wait", action="store_true",
                    help="Block until the player process exits (default: detach and return)")
    pl.add_argument("--pick-best-item", type=int, choices=[0, 1], default=0,
                    help="On ambiguous search results: 0=list and require --item-id (default), "
                         "1=auto-select best ≤1080p like batch")

    sy = sub.add_parser("sync", help="Sync all libraries (or one with --library)")
    sy.add_argument("--library", "-l", default=env("EMBY_LIBRARY"), help="Specific library to sync (env: EMBY_LIBRARY)")
    sy.add_argument("--output", "-o", default=env("EMBY_OUTPUT", DEFAULT_OUTPUT),
                    help=f"Output directory (env: EMBY_OUTPUT, default: {DEFAULT_OUTPUT})")
    sy.add_argument("--force", "-f", action="store_true", help="Re-download even if file exists with matching size")
    sy.add_argument("--throttle", "-t", type=float, nargs="?", const=1.0, default=0,
                    help="Limit speed to playback rate. Optional multiplier: 1=realtime, 1.5=50%% faster (default: off)")
    sy.add_argument("--method", "-m", default=env("EMBY_METHOD", "download"),
                    choices=["download", "stream", "hls"],
                    help="Download method: 'download' (API Download), 'stream' (browser-like original.*), "
                         "or 'hls' (stream chunks + remux) (env: EMBY_METHOD)")

    ba = sub.add_parser("batch", help="Download titles from a text file (movies, seasons, episodes)")
    ba.add_argument("--file", "-F", required=True, help="Text file with one title per line")
    ba.add_argument("--dry-run", "-n", action="store_true", help="Search and select only, do not download")
    ba.add_argument("--output", "-o", default=env("EMBY_OUTPUT", DEFAULT_OUTPUT),
                    help=f"Output directory (env: EMBY_OUTPUT, default: {DEFAULT_OUTPUT})")
    ba.add_argument("--force", "-f", action="store_true", help="Re-download even if file exists with matching size")
    ba.add_argument("--throttle", "-t", type=float, nargs="?", const=1.0, default=0,
                    help="Limit speed to playback rate. Optional multiplier: 1=realtime, 1.5=50%% faster (default: off)")
    ba.add_argument("--method", "-m", default=env("EMBY_METHOD", "download"),
                    choices=["download", "stream", "hls"],
                    help="Download method: 'download' (API Download), 'stream' (browser-like original.*), "
                         "or 'hls' (stream chunks + remux) (env: EMBY_METHOD)")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.server:
        parser.error("Provide --server or set EMBY_SERVER")

    if not args.api_key and not args.username:
        parser.error("Provide --api-key / EMBY_API_KEY or --username / EMBY_USERNAME")

    client = EmbyClient(args.server, api_key=args.api_key)

    if args.username is not None:
        pw = args.password if args.password is not None else ""
        print(f"Authenticating as '{args.username}'...")
        try:
            client.authenticate(args.username, pw)
        except requests.HTTPError as exc:
            print(f"Authentication failed: {exc}")
            sys.exit(1)
        print("OK\n")

    commands = {
        "list": cmd_list,
        "download": cmd_download,
        "search": cmd_search,
        "play": cmd_play,
        "sync": cmd_sync,
        "batch": cmd_batch,
    }
    commands[args.command](client, args)


if __name__ == "__main__":
    main()
