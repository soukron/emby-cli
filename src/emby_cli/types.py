"""Structured types for Emby API responses.

All TypedDicts use ``total=False`` because the Emby API does not guarantee
every field in every response — the set of returned keys depends on the
``Fields`` query parameter, server version, and item type.

Compatible with Python 3.9+ (``from __future__ import annotations`` enables
``list[X]`` syntax in annotations without requiring ``typing.List``).
"""

from __future__ import annotations

from typing import TypedDict


class MediaStream(TypedDict, total=False):
    """A single audio, video, or subtitle stream within a MediaSource."""

    Type: str
    Width: int


class MediaSource(TypedDict, total=False):
    """One media file / version attached to an item."""

    Id: str
    Size: int
    Container: str
    MediaStreams: list[MediaStream]
    DirectStreamUrl: str
    SupportsDirectStream: bool
    SupportsTranscoding: bool


class EmbyItem(TypedDict, total=False):
    """A media item (movie, episode, audio, series, etc.)."""

    Id: str
    Name: str
    Type: str
    ProductionYear: int
    SeriesName: str
    ParentIndexNumber: int
    IndexNumber: int
    DateCreated: str
    Overview: str
    Genres: list[str]
    CommunityRating: float
    OfficialRating: str
    Container: str
    Status: str
    ChildCount: int
    RecursiveItemCount: int
    Path: str
    RunTimeTicks: int
    Width: int
    MediaSources: list[MediaSource]
    MediaStreams: list[MediaStream]


class EmbyUser(TypedDict, total=False):
    """User object returned by authentication or /Users endpoints."""

    Id: str
    Name: str


class AuthResponse(TypedDict, total=False):
    """Response from ``POST /Users/AuthenticateByName``."""

    AccessToken: str
    User: EmbyUser


class SystemInfo(TypedDict, total=False):
    """Server info from ``/System/Info`` or ``/System/Info/Public``."""

    ServerName: str
    Version: str
    OperatingSystem: str
    OperatingSystemDisplayName: str
    Id: str
    HasUpdateAvailable: bool
    LocalAddress: str
    WanAddress: str


class ItemsPage(TypedDict, total=False):
    """Paginated item list returned by ``/Users/{uid}/Items`` and similar."""

    Items: list[EmbyItem]
    TotalRecordCount: int


class LibraryView(TypedDict, total=False):
    """A library view from ``/Users/{uid}/Views``."""

    Id: str
    Name: str
    CollectionType: str
    Type: str


class PlaybackInfo(TypedDict, total=False):
    """Response from ``POST /Items/{id}/PlaybackInfo``."""

    PlaySessionId: str
    MediaSources: list[MediaSource]


class ItemCounts(TypedDict, total=False):
    """Aggregate counts from ``GET /Items/Counts``."""

    MovieCount: int
    SeriesCount: int
    EpisodeCount: int
    SongCount: int
    AlbumCount: int
    BoxSetCount: int
    BookCount: int
    TrailerCount: int
    MusicVideoCount: int
    ArtistCount: int
