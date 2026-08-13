"""help command — list available subcommands."""

from __future__ import annotations

# (name, one-line summary) — keep in sync with cli subparsers.
COMMAND_SUMMARIES: tuple[tuple[str, str], ...] = (
    ("help", "List available commands"),
    ("login", "Authenticate and cache an AccessToken"),
    ("logout", "Revoke cached AccessToken and delete local session"),
    ("config", "View and switch saved servers (credentials file)"),
    ("version", "Show emby-cli version"),
    ("info", "Show session user, server details, libraries, and item counts"),
    ("search", "Search media items or libraries"),
    ("show", "Show details for a media item or library by ID"),
    ("collection", "Search, manage, and download collections"),
    ("library", "Search, inspect, and download libraries"),
    ("item", "Search, inspect, play, and download media items"),
    ("download", "Download media items or libraries"),
    ("play", "Play a media item using an external player"),
)


def cmd_help() -> None:
    print("emby-cli — Emby media search / play / download\n")
    print("Commands:\n")
    width = max(len(name) for name, _ in COMMAND_SUMMARIES)
    for name, summary in COMMAND_SUMMARIES:
        print(f"  {name:<{width}}  {summary}")
    print("\nUse `emby-cli <command> -h` for options.")
    print("Global flags: --server / -s, --api-key / -k, --username / -u, --password / -p")
    print("Auth: API key, `login`/`logout`, or `config` contexts (`auth.json`).")
