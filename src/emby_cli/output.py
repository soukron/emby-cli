"""Homogeneous CLI progress / status messages."""

from __future__ import annotations

from dataclasses import dataclass, field


def prefix(idx: int | None = None, total: int | None = None) -> str:
    if idx is None or total is None:
        return ""
    return f"[{idx}/{total}] "


def print_download(
    label: str,
    dest,
    *,
    method: str,
    idx: int | None = None,
    total: int | None = None,
) -> None:
    print(f"{prefix(idx, total)}download ({method}): {label} -> {dest}")


def print_skip(
    label: str,
    dest,
    *,
    idx: int | None = None,
    total: int | None = None,
) -> None:
    print(f"{prefix(idx, total)}skip: {label} -> {dest}")


def print_error(
    message: str,
    *,
    idx: int | None = None,
    total: int | None = None,
) -> None:
    print(f"{prefix(idx, total)}error: {message}")


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)


@dataclass
class Stats:
    ok: int = 0
    skip: int = 0
    error: int = 0
    not_found: int = 0
    elapsed: float | None = None
    extras: dict = field(default_factory=dict)

    def exit_code(self, *, fail_on_not_found: bool = False) -> int:
        if self.error > 0:
            return 1
        if fail_on_not_found and self.not_found > 0:
            return 1
        return 0


def print_done(stats: Stats, *, label: str = "Done") -> None:
    parts = [
        f"ok={stats.ok}",
        f"skip={stats.skip}",
        f"error={stats.error}",
    ]
    if stats.not_found:
        parts.append(f"not_found={stats.not_found}")
    if stats.elapsed is not None:
        from emby_cli.util import format_duration

        parts.append(f"elapsed={format_duration(stats.elapsed)}")
    print(f"\n{label}. " + " ".join(parts))
