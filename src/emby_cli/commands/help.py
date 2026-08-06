"""help command — list available subcommands."""

from __future__ import annotations

# (name, one-line summary) — keep in sync with cli subparsers.
COMMAND_SUMMARIES: tuple[tuple[str, str], ...] = (
    ("help", "List available commands"),
    ("login", "Authenticate and cache an AccessToken"),
    ("version", "Show emby-cli version"),
    ("info", "Show session user, server details, libraries, and item counts"),
    ("search", "Search media items or libraries"),
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
    print("Auth: API key, `emby-cli login`, or username/password (AccessToken cached on disk).")
