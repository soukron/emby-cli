"""Resolve Emby connection settings from CLI args, env, or interactive prompts."""

from __future__ import annotations

import argparse
import os
import sys
from getpass import getpass


class CredentialError(Exception):
    """Missing or invalid credentials for the requested mode."""


def _from_args_or_env(args: argparse.Namespace | None, attr: str, env_key: str) -> str:
    if args is not None:
        value = getattr(args, attr, None)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return os.environ.get(env_key, "").strip()


def resolve_server(
    args: argparse.Namespace | None = None,
    *,
    prompt: bool = False,
) -> str:
    value = _from_args_or_env(args, "server", "EMBY_SERVER")
    if value:
        return value.rstrip("/")
    if prompt and sys.stdin.isatty():
        entered = input("Emby server URL: ").strip()
        if entered:
            return entered.rstrip("/")
    raise CredentialError("Provide --server or set EMBY_SERVER")


def resolve_username(
    args: argparse.Namespace | None = None,
    *,
    prompt: bool = False,
) -> str:
    value = _from_args_or_env(args, "username", "EMBY_USERNAME")
    if value:
        return value
    if prompt and sys.stdin.isatty():
        entered = input("Username: ").strip()
        if entered:
            return entered
    raise CredentialError("Provide --username / EMBY_USERNAME")


def resolve_password(
    args: argparse.Namespace | None = None,
    *,
    prompt: bool = False,
) -> str | None:
    """Password from args/env; optional interactive prompt.

    Returns ``None`` when not provided (operational commands cannot re-auth
    on 401 without a known password). Empty string is a valid password.
    """
    if args is not None and getattr(args, "password", None) is not None:
        return str(args.password)
    env = os.environ.get("EMBY_PASSWORD")
    if env is not None:
        return env
    if prompt and sys.stdin.isatty():
        return getpass("Password: ")
    if prompt:
        raise CredentialError(
            "EMBY_PASSWORD is required (set env or run interactively on a TTY)"
        )
    return None


def resolve_login_credentials(
    args: argparse.Namespace | None = None,
) -> tuple[str, str, str]:
    """Interactive login: env/flags first, then TTY prompts for gaps."""
    server = resolve_server(args, prompt=True)
    username = resolve_username(args, prompt=True)
    password = resolve_password(args, prompt=True)
    assert password is not None
    return server, username, password


def resolve_operational_auth(
    args: argparse.Namespace,
) -> tuple[str | None, str | None, str | None]:
    """Non-interactive: return (api_key, username, password).

    ``username`` / ``password`` may be ``None`` when unset (cache may still apply).
    """
    api_key = _from_args_or_env(args, "api_key", "EMBY_API_KEY") or None
    username_raw = _from_args_or_env(args, "username", "EMBY_USERNAME")
    username = username_raw or None
    password = resolve_password(args, prompt=False)
    return api_key, username, password
