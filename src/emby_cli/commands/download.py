"""download command — media item, library, or title file."""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from emby_cli.client import EmbyClient
from emby_cli.download_ops import (
    download_items,
    download_library_items,
    download_one_item,
    find_library,
    library_rows,
    match_libraries,
)
from emby_cli.mode_args import (
    mode_is_item,
    mode_is_library,
    resolve_item_id,
    resolve_query,
)
from emby_cli.output import Stats, print_done, print_error
from emby_cli.resolve import (
    print_available_libraries,
    print_library_choices,
    resolve_title_items,
)
from emby_cli.util import format_duration


@dataclass(frozen=True)
class DownloadOpts:
    """Download settings shared by every download mode."""

    output: Path
    throttle: float
    method: str
    dry_run: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "DownloadOpts":
        return cls(
            output=Path(args.output),
            throttle=float(getattr(args, "throttle", 0) or 0),
            method=getattr(args, "method", "download"),
            dry_run=bool(getattr(args, "dry_run", False)),
        )


def validate_download_args(args: argparse.Namespace) -> str | None:
    """Return an error message if mode/selectors are invalid; else ``None``."""
    if mode_is_item(args):
        query, err = resolve_query(args)
        if err:
            return err
        item_id = resolve_item_id(args, include_env=not query)
        if bool(item_id) == bool(query):
            return "With --item, provide exactly one of --id or QUERY/--search"
        return None

    if mode_is_library(args):
        if bool(getattr(args, "pick_best_item", False)):
            return "--pick-best-item cannot be used with --library"
        query, err = resolve_query(args)
        if err:
            return err
        library_id = (getattr(args, "id", None) or "").strip() or None
        if bool(library_id) == bool(query):
            return "With --library, provide exactly one of --id or QUERY/--search"
        return None

    if getattr(args, "from_file", None):
        if (getattr(args, "id", None) or "").strip() or (
            getattr(args, "search", None) or ""
        ).strip():
            return "With --from-file, do not pass --id or --search"
        return None

    return "Specify --item, --library, or --from-file"


def _cmd_download_item(client: EmbyClient, args: argparse.Namespace) -> None:
    opts = DownloadOpts.from_args(args)
    pick_best = bool(getattr(args, "pick_best_item", False))
    search, _ = resolve_query(args)
    item_id = resolve_item_id(args, include_env=not search)

    if opts.dry_run:
        print("*** DRY RUN — no files will be downloaded ***\n")

    if item_id:
        item_ids = [x.strip() for x in item_id.split(",") if x.strip()]
        items: list[dict] = []
        stats = Stats()
        total = len(item_ids)
        for idx, iid in enumerate(item_ids, 1):
            try:
                items.append(client.get_item_info(iid))
            except (requests.RequestException, RuntimeError) as exc:
                print_error(f"fetching item {iid}: {exc}", idx=idx, total=total)
                stats.error += 1
        if items:
            got = download_items(
                client,
                items,
                opts.output,
                method=opts.method,
                force=args.force,
                throttle=opts.throttle,
                dry_run=opts.dry_run,
            )
            stats.ok += got.ok
            stats.skip += got.skip
            stats.error += got.error
        print_done(stats)
        sys.exit(stats.exit_code())

    items = resolve_title_items(
        client,
        search,
        pick_best=pick_best,
        allow_season_all=True,
    )
    if items is None:
        sys.exit(1)

    stats = download_items(
        client,
        items,
        opts.output,
        method=opts.method,
        force=args.force,
        throttle=opts.throttle,
        dry_run=opts.dry_run,
    )
    print_done(stats)
    sys.exit(stats.exit_code())


def _cmd_download_library(client: EmbyClient, args: argparse.Namespace) -> None:
    opts = DownloadOpts.from_args(args)
    library_id = (getattr(args, "id", None) or "").strip() or None
    search, _ = resolve_query(args)

    if opts.dry_run:
        print("*** DRY RUN — no files will be downloaded ***\n")

    libraries = client.get_libraries()
    if library_id:
        lib = find_library(libraries, library_id=library_id)
        if not lib:
            print(f"Library id '{library_id}' not found. Available:")
            print_available_libraries(libraries)
            sys.exit(1)
    else:
        matches = match_libraries(libraries, search or "")
        if not matches:
            print(f"Library '{search}' not found. Available:")
            print_available_libraries(libraries)
            sys.exit(1)
        if len(matches) > 1:
            print(
                f"Multiple matches ({len(matches)}). "
                "Re-run with --id, for example:\n"
                f'  emby-cli download --library --id {matches[0].get("Id", "<id>")}'
            )
            print_library_choices(library_rows(client, matches))
            sys.exit(1)
        lib = matches[0]

    stats = download_library_items(
        client,
        lib,
        opts.output,
        method=opts.method,
        force=args.force,
        throttle=opts.throttle,
        show_section=True,
        dry_run=opts.dry_run,
    )
    print_done(stats)
    sys.exit(stats.exit_code())


def _cmd_download_from_file(client: EmbyClient, args: argparse.Namespace) -> None:
    opts = DownloadOpts.from_args(args)
    pick_best = bool(getattr(args, "pick_best_item", False))

    if opts.dry_run:
        print("*** DRY RUN — no files will be downloaded ***\n")

    file_path = Path(args.from_file)
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
            except (requests.RequestException, RuntimeError) as exc:
                print_error(str(exc))
                elapsed = time.monotonic() - line_t0
                line_stats.append((label, "ERROR", elapsed, str(exc)))
                totals.error += 1
                continue

            result = download_one_item(
                client,
                item,
                opts.output,
                method=opts.method,
                force=args.force,
                throttle=opts.throttle,
                dry_run=opts.dry_run,
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
                opts.output,
                method=opts.method,
                force=args.force,
                throttle=opts.throttle,
                dry_run=opts.dry_run,
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

        elapsed = time.monotonic() - line_t0
        if opts.dry_run:
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
    print(f"From-file complete in {format_duration(totals.elapsed)}\n")

    max_label = max((len(s[0]) for s in line_stats), default=10)
    for label, status, elapsed, detail in line_stats:
        time_str = format_duration(elapsed) if elapsed > 0 else "-"
        detail_str = f" ({detail})" if detail else ""
        dots = "." * (max_label - len(label) + 3)
        print(f"  {label} {dots} {time_str:<10} {status}{detail_str}")

    print_done(totals, label="From-file")
    sys.exit(totals.exit_code(fail_on_not_found=True))


def cmd_download(client: EmbyClient, args: argparse.Namespace) -> None:
    err = validate_download_args(args)
    if err:
        print(err)
        sys.exit(1)

    if mode_is_item(args):
        _cmd_download_item(client, args)
        return
    if mode_is_library(args):
        _cmd_download_library(client, args)
        return
    if getattr(args, "from_file", None):
        _cmd_download_from_file(client, args)
        return
    print("Specify --item, --library, or --from-file")
    sys.exit(1)
