"""Item command passes filters to the API instead of scanning the full catalog."""

from __future__ import annotations

from unittest.mock import patch

from emby_cli.cli import build_parser
from emby_cli.client import EmbyClient
from emby_cli.commands.item import cmd_item


def _client() -> EmbyClient:
    client = EmbyClient("http://host:8096", api_key="k")
    client.user_id = "uid"
    return client


def test_item_search_year_and_type_use_api_filters():
    client = _client()
    with patch.object(client.items, "search", return_value=([], 0)) as search:
        cmd_item(
            client,
            build_parser().parse_args(["item", "search", "--year", "2026", "--type", "movie"]),
        )
    search.assert_called_once_with(
        "",
        item_types="Movie",
        year=2026,
        limit=30,
        sort_by=None,
        desc=False,
        use_cache=True,
    )
