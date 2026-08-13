"""play command — legacy wrapper over item playback helpers."""

from __future__ import annotations

import argparse
import sys

from emby_cli.client import EmbyClient
from emby_cli.deprecation import warn_deprecated
from emby_cli.item_ops import find_player, play_item_ids, play_one_item
from emby_cli.mode_args import resolve_item_id, resolve_query
from emby_cli.output import print_error
from emby_cli.resolve import resolve_title_item


def validate_play_args(args: argparse.Namespace) -> str | None:
    """Return an error message if selectors are invalid; else ``None``."""
    query, err = resolve_query(args)
    if err:
        return err
    item_id = resolve_item_id(args, include_env=not query)
    pick_best = bool(getattr(args, "pick_best_item", False))

    if bool(item_id) == bool(query):
        return "Provide exactly one of --id or QUERY/--search"
    if item_id and pick_best:
        return "--pick-best-item can only be used with QUERY/--search"
    return None


def cmd_play(client: EmbyClient, args: argparse.Namespace) -> None:
    """Resolve DirectStreamUrl and open it in an external player."""
    warn_deprecated("play")
    err = validate_play_args(args)
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)

    query, _ = resolve_query(args)
    item_id = resolve_item_id(args, include_env=not query)
    pick_best = bool(getattr(args, "pick_best_item", False))
    wait = bool(getattr(args, "wait", False))

    try:
        player_cmd = find_player(getattr(args, "player", None))
    except RuntimeError as exc:
        print_error(str(exc))
        sys.exit(1)

    if item_id:
        rc = play_item_ids(client, item_id, player_cmd, wait=wait)
        if rc != 0:
            sys.exit(rc)
        return

    item = resolve_title_item(client, query, pick_best=pick_best)
    if item is None:
        sys.exit(1)
    rc = play_one_item(client, item, player_cmd, wait=wait)
    if rc != 0:
        sys.exit(rc)
