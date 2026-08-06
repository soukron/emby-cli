"""Title-line parsing, resolution ranking, and item resolution for play/batch."""

from __future__ import annotations

import re
from collections import defaultdict

from emby_cli.client import EmbyClient
from emby_cli.util import format_size, item_remote_size

_TITLE_RE = re.compile(
    r"^(.+?)"              # title (non-greedy)
    r"(?:\s*\((\d{4})\))?" # optional (YYYY)
    r"(?:\s+S(\d+)"        # optional S##
    r"(?:E(\d+))?"         # optional E##
    r")?$",
    re.IGNORECASE,
)


def parse_title_line(line: str) -> tuple[str, int | None, int | None, int | None]:
    """Parse 'Title', 'Title (2010)', 'Title S01', 'Title (2008) S01E05', etc."""
    line = line.strip()
    m = _TITLE_RE.match(line)
    if m:
        title = m.group(1).strip()
        year = int(m.group(2)) if m.group(2) else None
        season = int(m.group(3)) if m.group(3) else None
        episode = int(m.group(4)) if m.group(4) else None
        return title, season, episode, year
    return line, None, None, None


def item_video_width(item: dict) -> int | None:
    w = item.get("Width")
    if w:
        return w
    streams = item.get("MediaStreams", [])
    if not streams:
        sources = item.get("MediaSources", [])
        if sources:
            streams = sources[0].get("MediaStreams", [])
    for s in streams:
        if s.get("Type") == "Video" and s.get("Width"):
            return s["Width"]
    return None


def classify_resolution(width: int | None) -> str:
    if width is None:
        return "?"
    if width >= 3840:
        return "4K"
    if width >= 1920:
        return "1080p"
    if width >= 1280:
        return "720p"
    return "SD"


def pick_best_item(items: list[dict]) -> dict | None:
    """Pick the best resolution up to 1080p (skip 4K)."""
    if not items:
        return None
    if len(items) == 1:
        return items[0]

    classified = [(it, item_video_width(it) or 0) for it in items]

    for it, w in classified:
        if classify_resolution(w) == "1080p":
            return it

    non_4k = [(it, w) for it, w in classified if classify_resolution(w) != "4K"]
    if non_4k:
        non_4k.sort(key=lambda x: x[1], reverse=True)
        return non_4k[0][0]

    classified.sort(key=lambda x: x[1], reverse=True)
    return classified[0][0]


def item_label(item: dict) -> str:
    """Human-readable name; episodes include SxxExx prefix."""
    name = item.get("Name") or "?"
    if item.get("Type") == "Episode":
        s, e = item.get("ParentIndexNumber"), item.get("IndexNumber")
        if s is not None and e is not None:
            return f"S{s:02d}E{e:02d} {name}"
    return name


def print_item_choices(
    items: list[dict],
    *,
    selected: dict | None = None,
    excluded: set[str] | None = None,
) -> None:
    """Print a compact, uniform table of items (movies, series, episodes)."""
    if not items:
        return
    excluded = excluded or set()
    id_w = max(len("ID"), max(len(str(it.get("Id", ""))) for it in items))
    name_w = 44

    header = (
        f"{'ID':<{id_w}}  {'Name':<{name_w}}  {'Year':<4}  {'Type':<8}  "
        f"{'Res':>5}  {'Size':>9}"
    )
    print()
    print(header)
    print("-" * len(header))

    selected_id = selected.get("Id") if selected else None
    for it in items:
        iid = str(it.get("Id", ""))
        label = item_label(it)
        if selected_id is not None and iid == selected_id:
            label = f"* {label}"
        elif iid in excluded:
            label = f"- {label}"
        if len(label) > name_w:
            label = label[: name_w - 1] + "…"
        year = str(it.get("ProductionYear") or "?")
        itype = str(it.get("Type") or "?")
        res = classify_resolution(item_video_width(it))
        size = format_size(item_remote_size(it))
        print(
            f"{iid:<{id_w}}  {label:<{name_w}}  {year:<4}  {itype:<8}  "
            f"{res:>5}  {size:>9}"
        )


def print_library_choices(libraries: list[dict]) -> None:
    """Print libraries: ID, Name, Type, Items (no Year/Res/Size)."""
    if not libraries:
        return
    id_w = max(len("ID"), max(len(str(lib.get("Id", ""))) for lib in libraries))
    name_w = 44
    type_w = max(len("Type"), max(len(str(lib.get("Type") or "?")) for lib in libraries))
    items_w = max(len("Items"), 5)

    header = (
        f"{'ID':<{id_w}}  {'Name':<{name_w}}  {'Type':<{type_w}}  {'Items':>{items_w}}"
    )
    print()
    print(header)
    print("-" * len(header))

    for lib in libraries:
        iid = str(lib.get("Id", ""))
        label = str(lib.get("Name") or "?")
        if len(label) > name_w:
            label = label[: name_w - 1] + "…"
        itype = str(lib.get("Type") or "?")
        count = lib.get("ItemCount")
        count_s = str(count) if count is not None else "?"
        print(
            f"{iid:<{id_w}}  {label:<{name_w}}  {itype:<{type_w}}  {count_s:>{items_w}}"
        )


def _ambiguous(
    items: list[dict],
    *,
    excluded: set[str] | None = None,
    hint: str = (
        "Use --item-id with an ID from the list above, "
        "or pass --pick-best-item to auto-select."
    ),
) -> None:
    print_item_choices(items, excluded=excluded)
    print(f"\n{hint}")


def _pick_episode_versions(episodes: list[dict], *, pick_best: bool) -> list[dict] | None:
    """Collapse multiple versions per SxxExx. Returns None if ambiguous without pick_best."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for ep in episodes:
        key = (ep.get("ParentIndexNumber"), ep.get("IndexNumber"))
        groups[key].append(ep)

    chosen: list[dict] = []
    for key in sorted(groups.keys(), key=lambda k: (k[0] or 0, k[1] or 0)):
        versions = groups[key]
        if len(versions) == 1:
            chosen.append(versions[0])
            continue
        if not pick_best:
            print(f"  Multiple versions for S{key[0] or 0:02d}E{key[1] or 0:02d}; ambiguous:")
            _ambiguous(versions)
            return None
        best = pick_best_item(versions)
        if best is None:
            _ambiguous(versions)
            return None
        print_item_choices(versions, selected=best)
        chosen.append(best)
    return chosen


def resolve_title_items(
    client: EmbyClient,
    raw_line: str,
    *,
    pick_best: bool = False,
    allow_season_all: bool = False,
) -> list[dict] | None:
    """Resolve a title line to one or more items (strict).

    Returns a list of items to act on, or None on not-found / ambiguity.
    When *allow_season_all* is True (batch) and the line is ``Sxx`` without
    ``Exx``, returns all episodes in that season (with optional pick_best per
    episode version). When False (play), season-only lines refuse.
    """
    title, season, episode, year = parse_title_line(raw_line)

    if season is not None:
        kind = f"S{season:02d}E{episode:02d}" if episode is not None else f"S{season:02d}"
        label = f"{title} ({year}) {kind}" if year else f"{title} {kind}"
        print(f"Searching: \"{label}\" (series)")

        series_results = client.search_items(title, item_types="Series")
        if not series_results:
            print("No series found.")
            return None

        candidates = series_results
        excluded: set[str] = set()
        if year is not None:
            year_matches = [s for s in series_results if s.get("ProductionYear") == year]
            if year_matches:
                print(f"  Year filter: {year} ({len(year_matches)}/{len(series_results)} match)")
                excluded = {s["Id"] for s in series_results if s not in year_matches}
                candidates = year_matches
            else:
                print(f"  No series match year {year}.")
                _ambiguous(series_results)
                return None

        if len(candidates) > 1:
            print("  Multiple series matches; pick one with --item-id:")
            _ambiguous(series_results, excluded=excluded)
            return None

        series = candidates[0]
        print(f"  Found series: {series['Name']} ({series.get('ProductionYear', '?')})")

        episodes = client.get_show_episodes(series["Id"], season=season)
        if episode is not None:
            episodes = [e for e in episodes if e.get("IndexNumber") == episode]

        if not episodes:
            print(f"  No episodes found for {kind}.")
            return None

        if episode is None:
            if not allow_season_all:
                print(f"  Season {season:02d} has {len(episodes)} episode(s); "
                      "specify SxxExx or --item-id:")
                print_item_choices(episodes)
                return None
            picked = _pick_episode_versions(episodes, pick_best=pick_best)
            return picked

        if len(episodes) == 1:
            return [episodes[0]]

        if not pick_best:
            print(f"  {len(episodes)} versions for {kind}; ambiguous:")
            _ambiguous(episodes)
            return None

        best = pick_best_item(episodes)
        if best is None:
            _ambiguous(episodes)
            return None
        print_item_choices(episodes, selected=best)
        return [best]

    # Movie path
    label = f"{title} ({year})" if year else title
    print(f"Searching: \"{label}\" (movie)")
    results = client.search_items(title, item_types="Movie")
    if not results:
        print("No results found.")
        return None

    candidates = results
    excluded: set[str] = set()
    if year is not None:
        year_matches = [r for r in results if r.get("ProductionYear") == year]
        if year_matches:
            print(f"  Year filter: {year} ({len(year_matches)}/{len(results)} match)")
            excluded = {r["Id"] for r in results if r not in year_matches}
            candidates = year_matches
        else:
            print(f"  No results match year {year}.")
            _ambiguous(results)
            return None

    if len(candidates) == 1:
        best = candidates[0]
        print_item_choices(results, selected=best, excluded=excluded)
        return [best]

    if not pick_best:
        print(f"  {len(candidates)} matches; ambiguous:")
        _ambiguous(results, excluded=excluded)
        return None

    best = pick_best_item(candidates)
    if best is None:
        _ambiguous(candidates)
        return None

    print_item_choices(results, selected=best, excluded=excluded)
    return [best]


def resolve_title_item(
    client: EmbyClient,
    raw_line: str,
    *,
    pick_best: bool = False,
) -> dict | None:
    """Resolve to a single item (play). Season-only lines are refused."""
    items = resolve_title_items(
        client, raw_line, pick_best=pick_best, allow_season_all=False
    )
    if not items:
        return None
    return items[0]
