"""config command — manage credentials file (kubectl-style)."""

from __future__ import annotations

import argparse
import json
import sys

from emby_cli.auth_cache import (
    auth_store_path,
    display_name,
    get_active_entry,
    list_contexts,
    load_store,
    rename_context_alias,
    set_current_context,
)


def cmd_config_current_server(_args: argparse.Namespace) -> None:
    active = get_active_entry()
    if active is None:
        print("error: no current server", file=sys.stderr)
        sys.exit(1)
    print(display_name(active))


def cmd_config_get_servers(_args: argparse.Namespace) -> None:
    store = load_store()
    contexts = list_contexts()
    if not contexts:
        print("No servers found.")
        return

    rows = []
    for ctx in contexts:
        current = "*" if ctx.name == store.current_context else ""
        rows.append((current, display_name(ctx), ctx.server_url, ctx.username))

    headers = ("CURRENT", "NAME", "SERVER", "USER")
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(row: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    print(fmt(headers))
    for row in rows:
        print(fmt(row))


def cmd_config_use_server(args: argparse.Namespace) -> None:
    name = (getattr(args, "server_name", None) or "").strip()
    if not name:
        print("error: provide a server name", file=sys.stderr)
        sys.exit(1)
    try:
        entry = set_current_context(name)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    label = display_name(entry)
    if label == entry.name:
        print(f"Switched to server {entry.name}")
    else:
        print(f'Switched to server "{label}" ({entry.name})')


def cmd_config_rename_server(args: argparse.Namespace) -> None:
    selector = (getattr(args, "server_name", None) or "").strip()
    alias = (getattr(args, "new_name", None) or "").strip()
    if not selector:
        print("error: provide a server name", file=sys.stderr)
        sys.exit(1)
    if not alias:
        print("error: provide --new-name", file=sys.stderr)
        sys.exit(1)
    try:
        entry = rename_context_alias(selector, alias)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f'Renamed server "{entry.name}" to "{display_name(entry)}"')


def cmd_config_view(_args: argparse.Namespace) -> None:
    store = load_store()
    path = auth_store_path()
    payload = {
        "current_context": store.current_context,
        "contexts": [
            {
                "name": c.name,
                "alias": c.alias or None,
                "server_url": c.server_url,
                "username": c.username,
                "access_token": "***",
                "user_id": c.user_id,
                "saved_at": c.saved_at,
            }
            for c in list_contexts()
        ],
    }
    print(f"# {path}")
    print(json.dumps(payload, indent=2))


def cmd_config(args: argparse.Namespace) -> None:
    sub = getattr(args, "config_command", None)
    handlers = {
        "current-server": cmd_config_current_server,
        "get-servers": cmd_config_get_servers,
        "use-server": cmd_config_use_server,
        "rename-server": cmd_config_rename_server,
        "view": cmd_config_view,
    }
    handler = handlers.get(sub) if sub else None
    if handler is None:
        print(
            "error: provide a config subcommand "
            "(current-server, get-servers, use-server, rename-server, view)",
            file=sys.stderr,
        )
        sys.exit(1)
    handler(args)
