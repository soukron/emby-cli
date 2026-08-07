"""Helpers for ``--item`` / ``--library`` optional QUERY mode flags."""

from __future__ import annotations

import argparse
import os


def mode_is_item(args: argparse.Namespace) -> bool:
    return getattr(args, "item", None) is not None


def mode_is_library(args: argparse.Namespace) -> bool:
    return getattr(args, "library", None) is not None


def embedded_query(args: argparse.Namespace) -> str | None:
    """QUERY passed as value of ``--item`` / ``--library``, if any."""
    for attr in ("item", "library"):
        val = getattr(args, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def resolve_query(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Return ``(query, error)``. Query may come from mode flag or ``--search``."""
    embedded = embedded_query(args)
    flag = (getattr(args, "search", None) or "").strip() or None
    if embedded and flag:
        return None, "Do not pass --search when QUERY is given to --item / --library"
    return embedded or flag, None


def resolve_item_id(
    args: argparse.Namespace,
    *,
    include_env: bool = True,
) -> str | None:
    """Resolve ``--id``, optionally falling back to ``EMBY_ITEM_ID``."""
    item_id = (getattr(args, "id", None) or "").strip()
    if item_id:
        return item_id
    if not include_env:
        return None
    return (os.environ.get("EMBY_ITEM_ID") or "").strip() or None
