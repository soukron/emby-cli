"""Simple JSON disk cache for semi-static Emby API data."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from emby_cli.auth_cache import cache_dir

_DEFAULT_TTL_SECONDS = 600


def _data_dir() -> Path:
    return cache_dir() / "data"


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return _data_dir() / f"{digest}.json"


def ttl_seconds() -> int:
    raw = os.environ.get("EMBY_DATA_CACHE_TTL")
    if raw is None:
        return _DEFAULT_TTL_SECONDS
    try:
        val = int(raw)
    except ValueError:
        return _DEFAULT_TTL_SECONDS
    return max(0, val)


def load_json(key: str, *, ttl: int | None = None) -> object | None:
    path = _cache_path(key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    ts = data.get("saved_at")
    if not isinstance(ts, (int, float)):
        return None
    max_age = ttl_seconds() if ttl is None else max(0, int(ttl))
    if time.time() - float(ts) > max_age:
        return None
    return data.get("value")


def save_json(key: str, value: object) -> None:
    path = _cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at": time.time(),
        "value": value,
    }
    path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")


def delete_json(key: str) -> None:
    """Delete one cached value if present."""
    try:
        _cache_path(key).unlink(missing_ok=True)
    except OSError:
        # Cache invalidation must never turn a successful server mutation
        # into a failed CLI operation.
        pass
