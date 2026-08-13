"""Deprecation notices for legacy top-level commands."""

from __future__ import annotations

import sys

_LEGACY_REPLACEMENTS: dict[str, str] = {
    "search": "use `emby-cli item search`, `library search`, or `collection search`",
    "show": "use `emby-cli item show`, `library show`, or `collection show`",
    "play": "use `emby-cli item play`",
    "download": "use `emby-cli item download`, `library download`, or `collection download`",
}


def warn_deprecated(command: str) -> None:
    """Print a one-line deprecation warning to stderr."""
    replacement = _LEGACY_REPLACEMENTS.get(command)
    if not replacement:
        return
    print(
        f"warning: `{command}` is deprecated; {replacement}.",
        file=sys.stderr,
    )
