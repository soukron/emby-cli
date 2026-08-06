# Changelog

## Unreleased

- `version`: show emby-cli version; with valid server credentials also show Emby `/System/Info` version.
- `info`: session summary (user, url, server, version, os, id) plus library names and item counts from `GET /Items/Counts` (replaces draft `whoami`).
- `--pick-best-item` is a flag (presence enables auto-select); no longer takes `0`/`1`.
- `info` / `version` probe the server once (no retries); on failure show configured user/URL and mark server name/version as not validated.
- Note: `/Items/Counts` may count multiple versions of the same title higher than UI “items” views.
- `probe_session`: fall back to `/System/Info/Public` when full `/System/Info` is forbidden (non-admin users); still proceed with Views/Counts.

## 0.2.0

- API fixes: `get_item_info` Fields, `/Users/Me`, safer 416 resume, `api_key` on play URLs, client version from package, `/emby` base URL normalize, HLS without invalid `copy` codecs, paginated episodes.
- Shared resolve for `play`/`batch` (strict by default; `--pick-best-item` flag).
- Homogeneous CLI messages (`output.py`); shared library/download loops; non-zero exit on errors / batch not-found.
- `search`: paginate Emby results (was capped at 25); `--count` / `-n` to limit how many to return (default: all).
- More tests (`test_client`, `test_output`, parser coverage).
