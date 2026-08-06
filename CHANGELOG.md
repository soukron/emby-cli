# Changelog

## Unreleased

- Known issue (not fixed yet): `search`/`download`/`play` authenticate before validating required selectors (`--id`/`--search`/`--all`); see ops `AGENTS.md` → Deuda.

## 0.3.0

Breaking:

- Removed `batch`, `sync`, and `list` subcommands (`search --library --all` lists all libraries).
- `download` uses modes: `--media-item`, `--library`, or `--from-file` / `-F`, plus selectors `--id` or `--search`.
- `play` uses `--id` or `--search` (no positional query; `--item-id` removed).
- `search` uses `--media-item` / `--library` plus exactly one of `--id`, `--search`, or `--all`.
- `search --count` / `-n` defaults to 30 for both `--media-item` and `--library`.
- `search --media-item --all` probes `TotalRecordCount` and refuses if more than `--count` items (asks to use `--search`).
- `--dry-run` / `-n` works for all `download` modes.
- `--pick-best-item` for item title resolution (`download --media-item --search`, `--from-file`, `play --search`); not with `--library`.
- `help`: list available commands with a short summary (no server required).

## 0.2.2

- `version`: show emby-cli version; with valid server credentials also show Emby `/System/Info` version.
- `info`: session summary (user, url, server, version, os, id) plus library names and item counts from `GET /Items/Counts` (replaces draft `whoami`).
- `--pick-best-item` is a flag (presence enables auto-select); no longer takes `0`/`1`.
- `info` / `version` probe the server once (no retries); on failure show configured user/URL and mark server name/version as not validated.
- Note: `/Items/Counts` may count multiple versions of the same title higher than UI “items” views.
- `probe_session`: fall back to `/System/Info/Public` when full `/System/Info` is forbidden (non-admin users); still proceed with Views/Counts.
- Avoid broken `/Users/Me` on some Emby servers (HTTP 500 Guid format): use `User` from authenticate or `/Users/{id}`.
- `list`: library table is ID/Name/Type/Items (no Year/Res); gather all counts before printing; `list -l` keeps media table like `search`.

## 0.2.0

- API fixes: `get_item_info` Fields, `/Users/Me`, safer 416 resume, `api_key` on play URLs, client version from package, `/emby` base URL normalize, HLS without invalid `copy` codecs, paginated episodes.
- Shared resolve for `play`/`batch` (strict by default; `--pick-best-item` flag).
- Homogeneous CLI messages (`output.py`); shared library/download loops; non-zero exit on errors / batch not-found.
- `search`: paginate Emby results (was capped at 25); `--count` / `-n` to limit how many to return (default: all).
- More tests (`test_client`, `test_output`, parser coverage).
