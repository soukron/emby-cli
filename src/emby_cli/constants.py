"""Shared constants for emby-cli."""

DEFAULT_CHUNK = 8 * 1024 * 1024  # 8 MiB per read
TICKS_PER_SECOND = 10_000_000  # Emby RunTimeTicks resolution
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 30  # seconds; doubles each retry: 30, 60, 120, 240, 480
CLIENT_NAME = "emby-cli"
DEVICE_NAME = "emby-cli"
DEFAULT_OUTPUT = "./downloads"
