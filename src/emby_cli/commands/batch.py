"""batch command — download titles from a text file."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from emby_cli.client import EmbyClient
from emby_cli.download_ops import do_download, should_skip_item
from emby_cli.resolve import (
    classify_resolution,
    item_video_width,
    parse_title_line,
    pick_best_item,
)
from emby_cli.util import (
    build_dest_path,
    format_duration,
    format_size,
    item_remote_size,
)

def cmd_batch(client: EmbyClient, args: argparse.Namespace) -> None:
    """Download titles listed in a text file, with resolution prioritisation."""
    output = Path(args.output)
    throttle = getattr(args, "throttle", 0)
    method = getattr(args, "method", "download")
    dry_run = getattr(args, "dry_run", False)

    if dry_run:
        print("*** DRY RUN — no files will be downloaded ***\n")

    file_path = Path(args.file)
    lines: list[str] = []
    with open(file_path) as f:
        for raw in f:
            raw = raw.strip()
            if raw and not raw.startswith("#"):
                lines.append(raw)

    if not lines:
        print("No titles found in file.")
        return

    print(f"Loaded {len(lines)} titles from {file_path}\n")

    stats: list[tuple[str, str, float, str]] = []
    total_t0 = time.monotonic()

    for idx, raw_line in enumerate(lines, 1):
        emby_id_match = re.match(r"^embyId=(\S+)$", raw_line.strip(), re.IGNORECASE)
        if emby_id_match:
            item_id = emby_id_match.group(1)
            label = f"embyId={item_id}"
            print(f"\n[{idx}/{len(lines)}] Direct ID: {item_id}")
            line_t0 = time.monotonic()
            try:
                item = client.get_item_info(item_id)
                res = classify_resolution(item_video_width(item))
                size = format_size(item_remote_size(item))
                dest = build_dest_path(item, output)
                print(f"  {item['Name']} ({item.get('ProductionYear','?')}) [{res}, {size}]")

                if dry_run:
                    print(f"  Would download: {item['Name']} [{res}] -> {dest}")
                    stats.append((label, "DRY RUN", 0, item['Name']))
                    continue

                if should_skip_item(item, dest, method, args.force):
                    elapsed = time.monotonic() - line_t0
                    print(f"  Skipping (already downloaded)")
                    stats.append((label, "SKIPPED", elapsed, item['Name']))
                    continue

                print(f"  Downloading -> {dest}")
                do_download(client, item_id, item, dest, method, throttle)
                elapsed = time.monotonic() - line_t0
                print(f"  Time: {format_duration(elapsed)}")
                stats.append((label, "OK", elapsed, item['Name']))
            except Exception as exc:
                elapsed = time.monotonic() - line_t0
                print(f"  ERROR: {exc}")
                stats.append((label, "ERROR", elapsed, str(exc)))
            continue

        title, season, episode, year = parse_title_line(raw_line)

        if season is not None:
            kind = f"S{season:02d}E{episode:02d}" if episode else f"S{season:02d}"
            label = f"{title} ({year}) {kind}" if year else f"{title} {kind}"
            search_type = "series"
        else:
            label = f"{title} ({year})" if year else title
            search_type = "movie"

        print(f"\n[{idx}/{len(lines)}] Searching: \"{label}\" ({search_type})")
        line_t0 = time.monotonic()

        try:
            if search_type == "movie":
                results = client.search_items(title, item_types="Movie")
                if not results:
                    print("  No results found, skipping.")
                    stats.append((label, "NOT FOUND", 0, ""))
                    continue

                candidates = results
                if year is not None:
                    year_matches = [r for r in results if r.get("ProductionYear") == year]
                    if year_matches:
                        print(f"  Year filter: {year} ({len(year_matches)}/{len(results)} match)")
                        candidates = year_matches
                    else:
                      print(f"  WARNING: no results match year {year}, using all {len(results)} results")

                best = pick_best_item(candidates)
                for r in results:
                    res = classify_resolution(item_video_width(r))
                    size = format_size(item_remote_size(r))
                    selected = " <-- selected" if r is best else ""
                    excluded = " (excluded by year)" if year and r not in candidates else ""
                    print(f"    - {r['Name']} ({r.get('ProductionYear','?')}) [{res}, {size}]{selected}{excluded}")

                res = classify_resolution(item_video_width(best))
                dest = build_dest_path(best, output)

                if dry_run:
                    print(f"  Would download: {best['Name']} [{res}] -> {dest}")
                    stats.append((label, "DRY RUN", 0, ""))
                    continue

                if should_skip_item(best, dest, method, args.force):
                    elapsed = time.monotonic() - line_t0
                    print(f"  Skipping (already downloaded)")
                    stats.append((label, "SKIPPED", elapsed, ""))
                    continue

                print(f"  Downloading: {best['Name']} [{res}] -> {dest}")
                do_download(client, best["Id"], best, dest, method, throttle)
                elapsed = time.monotonic() - line_t0
                print(f"  Time: {format_duration(elapsed)}")
                stats.append((label, "OK", elapsed, ""))

            else:
                series_results = client.search_items(title, item_types="Series")
                if not series_results:
                    print("  No series found, skipping.")
                    stats.append((label, "NOT FOUND", 0, ""))
                    continue

                if year is not None:
                    year_matches = [s for s in series_results if s.get("ProductionYear") == year]
                    if year_matches:
                        print(f"  Year filter: {year} ({len(year_matches)}/{len(series_results)} match)")
                        for s in series_results:
                            tag = " <-- selected" if s is year_matches[0] else ""
                            excluded = " (excluded by year)" if s not in year_matches else ""
                            print(f"    - {s['Name']} ({s.get('ProductionYear','?')}){tag}{excluded}")
                        series = year_matches[0]
                    else:
                        print(f"  WARNING: no series match year {year}, using first result")
                        series = series_results[0]
                else:
                    series = series_results[0]

                print(f"  Found series: {series['Name']} ({series.get('ProductionYear','?')})")

                episodes = client.get_show_episodes(series["Id"], season=season)
                if episode is not None:
                    episodes = [e for e in episodes if e.get("IndexNumber") == episode]

                if not episodes:
                    print(f"  No episodes found for {kind}, skipping.")
                    stats.append((label, "NOT FOUND", 0, ""))
                    continue

                print(f"  {len(episodes)} episode(s)")

                if dry_run:
                    for ep_idx, ep in enumerate(episodes, 1):
                        ep_num = f"S{ep.get('ParentIndexNumber', 0):02d}E{ep.get('IndexNumber', 0):02d}"
                        ep_name = ep.get("Name", "?")
                        res = classify_resolution(item_video_width(ep))
                        size = format_size(item_remote_size(ep))
                        print(f"  [{ep_idx}/{len(episodes)}] {ep_num} {ep_name} [{res}, {size}]")
                    stats.append((label, "DRY RUN", 0, f"{len(episodes)} episodes"))
                    continue

                ep_errors = 0

                for ep_idx, ep in enumerate(episodes, 1):
                    ep_num = f"S{ep.get('ParentIndexNumber', 0):02d}E{ep.get('IndexNumber', 0):02d}"
                    ep_name = ep.get("Name", "?")
                    res = classify_resolution(item_video_width(ep))
                    size = format_size(item_remote_size(ep))
                    dest = build_dest_path(ep, output)

                    if should_skip_item(ep, dest, method, args.force):
                        print(f"  [{ep_idx}/{len(episodes)}] {ep_num} {ep_name} [{res}] - skipped")
                        continue

                    print(f"  [{ep_idx}/{len(episodes)}] {ep_num} {ep_name} [{res}, {size}]")
                    try:
                        do_download(client, ep["Id"], ep, dest, method, throttle)
                    except Exception as exc:
                        print(f"    ERROR: {exc}")
                        ep_errors += 1

                elapsed = time.monotonic() - line_t0
                detail = f"{len(episodes)} episodes"
                if ep_errors:
                    detail += f", {ep_errors} errors"
                status = "OK" if not ep_errors else "PARTIAL"
                print(f"  Time: {format_duration(elapsed)}")
                stats.append((label, status, elapsed, detail))

        except Exception as exc:
            elapsed = time.monotonic() - line_t0
            print(f"  ERROR: {exc}")
            stats.append((label, "ERROR", elapsed, str(exc)))

    total_elapsed = time.monotonic() - total_t0

    print(f"\n{'='*60}")
    print(f"Batch complete in {format_duration(total_elapsed)}\n")

    max_label = max(len(s[0]) for s in stats) if stats else 10
    for label, status, elapsed, detail in stats:
        time_str = format_duration(elapsed) if elapsed > 0 else "-"
        detail_str = f" ({detail})" if detail else ""
        dots = "." * (max_label - len(label) + 3)
        print(f"  {label} {dots} {time_str:<10} {status}{detail_str}")

    counts: dict[str, int] = {}
    for _, status, _, _ in stats:
        counts[status] = counts.get(status, 0) + 1

    print(f"\nDownloaded: {counts.get('OK', 0)}, Skipped: {counts.get('SKIPPED', 0)}, "
          f"Not found: {counts.get('NOT FOUND', 0)}, Errors: {counts.get('ERROR', 0)}")
    if counts.get("PARTIAL"):
        print(f"Partial: {counts['PARTIAL']}")
    print(f"{'='*60}")
