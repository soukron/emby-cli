"""emby-cli — backup and stream media from an Emby server."""

from __future__ import annotations

import warnings

# macOS system Python uses LibreSSL; urllib3 v2 only warns (TLS still works).
# Must run before any import that pulls in requests/urllib3 (see client.py).
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

from emby_cli.client import EmbyClient
from emby_cli.version import get_version

__all__ = ["EmbyClient", "get_version"]
