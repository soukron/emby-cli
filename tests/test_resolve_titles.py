"""Tests for resolve_title_items / resolve_title_item (strict title resolution)."""

from __future__ import annotations

from unittest.mock import MagicMock

from emby_cli.resolve import resolve_title_item, resolve_title_items


def _movie(iid: str, name: str, year: int, width: int = 1920) -> dict:
    return {
        "Id": iid,
        "Name": name,
        "Type": "Movie",
        "ProductionYear": year,
        "Width": width,
        "MediaSources": [{"Size": 1000, "MediaStreams": [{"Type": "Video", "Width": width}]}],
    }


def _series(iid: str, name: str, year: int) -> dict:
    return {"Id": iid, "Name": name, "Type": "Series", "ProductionYear": year}


def _episode(iid: str, name: str, season: int, ep: int, width: int = 1920) -> dict:
    return {
        "Id": iid,
        "Name": name,
        "Type": "Episode",
        "ParentIndexNumber": season,
        "IndexNumber": ep,
        "Width": width,
        "MediaSources": [{"Size": 500, "MediaStreams": [{"Type": "Video", "Width": width}]}],
    }


def test_movie_year_no_match_returns_none(capsys):
    client = MagicMock()
    client.search_items.return_value = [
        _movie("1", "Inception", 2010),
        _movie("2", "Inception", 2020),
    ]
    assert resolve_title_items(client, "Inception (1999)") is None
    out = capsys.readouterr().out
    assert "No results match year 1999" in out


def test_movie_unique_year_match(capsys):
    client = MagicMock()
    client.search_items.return_value = [
        _movie("1", "Inception", 2010),
        _movie("2", "Inception", 2020),
    ]
    items = resolve_title_items(client, "Inception (2010)")
    assert items is not None
    assert len(items) == 1
    assert items[0]["Id"] == "1"
    assert "Year filter: 2010" in capsys.readouterr().out


def test_movie_ambiguous_without_pick_best(capsys):
    client = MagicMock()
    client.search_items.return_value = [
        _movie("1", "Matrix", 1999, 1920),
        _movie("2", "Matrix", 1999, 3840),
    ]
    assert resolve_title_items(client, "Matrix (1999)") is None
    assert "ambiguous" in capsys.readouterr().out.lower()


def test_movie_pick_best_prefers_1080p_over_4k(capsys):
    client = MagicMock()
    client.search_items.return_value = [
        _movie("4k", "Matrix", 1999, 3840),
        _movie("1080", "Matrix", 1999, 1920),
    ]
    items = resolve_title_items(client, "Matrix (1999)", pick_best=True)
    assert items is not None
    assert items[0]["Id"] == "1080"


def test_series_ambiguous_returns_none(capsys):
    client = MagicMock()
    client.search_items.return_value = [
        _series("a", "Show", 2008),
        _series("b", "Show", 2008),
    ]
    assert resolve_title_items(client, "Show (2008) S01E01") is None
    assert "Multiple series matches" in capsys.readouterr().out
    client.get_show_episodes.assert_not_called()


def test_series_episode_unique():
    client = MagicMock()
    client.search_items.return_value = [_series("s1", "Show", 2008)]
    client.get_show_episodes.return_value = [
        _episode("e1", "Pilot", 1, 1),
        _episode("e2", "Next", 1, 2),
    ]
    items = resolve_title_items(client, "Show (2008) S01E01")
    assert items is not None
    assert items[0]["Id"] == "e1"
    client.get_show_episodes.assert_called_once_with("s1", season=1)


def test_series_episode_versions_ambiguous_without_pick_best(capsys):
    client = MagicMock()
    client.search_items.return_value = [_series("s1", "Show", 2008)]
    client.get_show_episodes.return_value = [
        _episode("v1", "Pilot", 1, 1, 1920),
        _episode("v2", "Pilot", 1, 1, 3840),
    ]
    assert resolve_title_items(client, "Show S01E01") is None
    assert "versions" in capsys.readouterr().out.lower()


def test_series_episode_versions_pick_best():
    client = MagicMock()
    client.search_items.return_value = [_series("s1", "Show", 2008)]
    client.get_show_episodes.return_value = [
        _episode("v4k", "Pilot", 1, 1, 3840),
        _episode("v1080", "Pilot", 1, 1, 1920),
    ]
    items = resolve_title_items(client, "Show S01E01", pick_best=True)
    assert items is not None
    assert items[0]["Id"] == "v1080"


def test_season_only_refused_without_allow_season_all(capsys):
    client = MagicMock()
    client.search_items.return_value = [_series("s1", "Show", 2008)]
    client.get_show_episodes.return_value = [
        _episode("e1", "A", 1, 1),
        _episode("e2", "B", 1, 2),
    ]
    assert resolve_title_items(client, "Show S01", allow_season_all=False) is None
    assert "specify SxxExx" in capsys.readouterr().out


def test_season_only_downloads_all_with_allow_season_all():
    client = MagicMock()
    client.search_items.return_value = [_series("s1", "Show", 2008)]
    client.get_show_episodes.return_value = [
        _episode("e1", "A", 1, 1),
        _episode("e2", "B", 1, 2),
    ]
    items = resolve_title_items(client, "Show S01", allow_season_all=True)
    assert items is not None
    assert [i["Id"] for i in items] == ["e1", "e2"]


def test_resolve_title_item_returns_single():
    client = MagicMock()
    client.search_items.return_value = [_movie("1", "Solo", 2010)]
    item = resolve_title_item(client, "Solo (2010)")
    assert item is not None
    assert item["Id"] == "1"


def test_resolve_title_item_season_only_refused():
    client = MagicMock()
    client.search_items.return_value = [_series("s1", "Show", 2008)]
    client.get_show_episodes.return_value = [_episode("e1", "A", 1, 1)]
    assert resolve_title_item(client, "Show S01") is None
