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
    ("search", "[deprecated] Search media items or libraries — use item/library/collection search"),
    ("show", "[deprecated] Show details for a media item or library — use item/library/collection show"),
    ("collection", "Search, manage, play, and download collections"),
    ("library", "Search, inspect, play, and download libraries"),
    ("item", "Search, inspect, play, and download media items"),
    ("download", "[deprecated] Download media items or libraries — use item/library/collection download"),
    ("play", "[deprecated] Play a media item — use item play"),
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
