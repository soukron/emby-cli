from __future__ import annotations


def get_version() -> str:
    try:
        from emby_cli._version import __version__

        return __version__
    except ImportError:
        pass

    try:
        from importlib.metadata import version

        return version("emby-cli")
    except Exception:
        return "unknown"
