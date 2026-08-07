"""Helpers for ``--item`` / ``--library`` optional QUERY mode flags."""

from __future__ import annotations

import argparse


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
