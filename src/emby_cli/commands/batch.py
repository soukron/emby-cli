"""batch command — download titles from a text file."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from emby_cli.client import EmbyClient
from emby_cli.download_ops import download_one_item
from emby_cli.output import Stats, print_done, print_error
from emby_cli.resolve import resolve_title_items
from emby_cli.util import format_duration


def cmd_batch(client: EmbyClient, args: argparse.Namespace) -> None:
    """Download titles listed in a text file (strict resolve + optional pick-best)."""
    output = Path(args.output)
    throttle = float(getattr(args, "throttle", 0) or 0)
    method = getattr(args, "method", "download")
    dry_run = bool(getattr(args, "dry_run", False))
    pick_best = bool(getattr(args, "pick_best_item", 0))

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

    line_stats: list[tuple[str, str, float, str]] = []
    totals = Stats()
    total_t0 = time.monotonic()

    for idx, raw_line in enumerate(lines, 1):
        emby_id_match = re.match(r"^embyId=(\S+)$", raw_line.strip(), re.IGNORECASE)
        line_t0 = time.monotonic()

        if emby_id_match:
            item_id = emby_id_match.group(1)
            label = f"embyId={item_id}"
            print(f"\n[{idx}/{len(lines)}] Direct ID: {item_id}")
            try:
                item = client.get_item_info(item_id)
            except Exception as exc:
                print_error(str(exc))
                elapsed = time.monotonic() - line_t0
                line_stats.append((label, "ERROR", elapsed, str(exc)))
                totals.error += 1
                continue

            result = download_one_item(
                client,
                item,
                output,
                method=method,
                force=args.force,
                throttle=throttle,
                dry_run=dry_run,
            )
            elapsed = time.monotonic() - line_t0
            status_map = {
                "ok": "OK",
                "skip": "SKIPPED",
                "error": "ERROR",
                "dry_run": "DRY RUN",
            }
            status = status_map.get(result, "ERROR")
            line_stats.append((label, status, elapsed, item.get("Name", "")))
            if result == "ok":
                totals.ok += 1
            elif result == "skip":
                totals.skip += 1
            elif result == "error":
                totals.error += 1
            continue

        label = raw_line
        print(f"\n[{idx}/{len(lines)}] {raw_line}")
        items = resolve_title_items(
            client,
            raw_line,
            pick_best=pick_best,
            allow_season_all=True,
        )
        if items is None:
            elapsed = time.monotonic() - line_t0
            line_stats.append((label, "NOT FOUND", elapsed, ""))
            totals.not_found += 1
            continue

        line_ok = line_skip = line_err = 0
        for item in items:
            result = download_one_item(
                client,
                item,
                output,
                method=method,
                force=args.force,
                throttle=throttle,
                dry_run=dry_run,
            )
            if result == "ok":
                line_ok += 1
                totals.ok += 1
            elif result == "skip":
                line_skip += 1
                totals.skip += 1
            elif result == "error":
                line_err += 1
                totals.error += 1
            # dry_run: no counters

        elapsed = time.monotonic() - line_t0
        if dry_run:
            status = "DRY RUN"
            detail = f"{len(items)} items"
        elif line_err and line_ok:
            status = "PARTIAL"
            detail = f"ok={line_ok} skip={line_skip} error={line_err}"
        elif line_err:
            status = "ERROR"
            detail = f"error={line_err}"
        elif line_ok:
            status = "OK"
            detail = f"{line_ok} items" if len(items) > 1 else ""
        else:
            status = "SKIPPED"
            detail = f"{line_skip} skipped" if line_skip else ""

        line_stats.append((label, status, elapsed, detail))

    totals.elapsed = time.monotonic() - total_t0

    print(f"\n{'=' * 60}")
    print(f"Batch complete in {format_duration(totals.elapsed)}\n")

    max_label = max((len(s[0]) for s in line_stats), default=10)
    for label, status, elapsed, detail in line_stats:
        time_str = format_duration(elapsed) if elapsed > 0 else "-"
        detail_str = f" ({detail})" if detail else ""
        dots = "." * (max_label - len(label) + 3)
        print(f"  {label} {dots} {time_str:<10} {status}{detail_str}")

    print_done(totals, label="Batch")
    sys.exit(totals.exit_code(fail_on_not_found=True))
