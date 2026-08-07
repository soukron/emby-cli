"""Shared constants for emby-cli."""

DEFAULT_CHUNK = 8 * 1024 * 1024  # 8 MiB per read
TICKS_PER_SECOND = 10_000_000  # Emby RunTimeTicks resolution
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 30  # seconds; doubles each retry: 30, 60, 120, 240, 480
# Single-shot probes (version / info): no backoff spam on unreachable servers
INFO_TIMEOUT = 10  # seconds
INFO_RETRIES = 1
CLIENT_NAME = "emby-cli"
DEVICE_NAME = "emby-cli"
DEFAULT_OUTPUT = "./downloads"
DOWNLOADABLE_TYPES = ("Movie", "Episode", "Audio", "Video")
SEARCH_ITEM_TYPES = ",".join(DOWNLOADABLE_TYPES)
# Library "recently added" / content counts: playable media only (no Studio, etc.).
SHOW_LIBRARY_ITEM_TYPES = "Movie,Episode,Audio"
# Default --count for search; also the soft cap that triggers --media-item --all refusal.
SEARCH_COUNT_DEFAULT = 30
ITEM_FIELDS = "Path,MediaSources,MediaStreams,Size,RunTimeTicks,ProductionYear,DateCreated"
# Extra fields for `show` detail view.
SHOW_ITEM_FIELDS = (
    ITEM_FIELDS
    + ",Overview,Genres,CommunityRating,OfficialRating,Container,"
    "SeriesName,Status,ChildCount,RecursiveItemCount"
)
SHOW_RECENT_COUNT = 10
