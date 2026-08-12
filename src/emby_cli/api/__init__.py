"""Entity-oriented services sharing one :class:`EmbyClient` transport."""

from emby_cli.api.collections import CollectionsService
from emby_cli.api.items import ItemsService

__all__ = ["CollectionsService", "ItemsService"]
