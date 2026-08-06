"""emby-cli — backup and stream media from an Emby server."""

from emby_cli.client import EmbyClient
from emby_cli.version import get_version

__all__ = ["EmbyClient", "get_version"]
