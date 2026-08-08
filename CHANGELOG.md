# Changelog

## Unreleased

- Expired/revoked sessions: print a clear `error:` on stderr (suggest `emby-cli login`) instead of an `HTTPError` traceback; drop the stale AccessToken from the local cache.
- Docs: public `AGENTS.md` for contributors (layout, auth, CLI contracts, tests, release).

## 0.5.2

Changed:

- Validation and per-item `error:` messages go to **stderr** (tables and normal progress stay on stdout), so scripts can separate data from failures.
- `download --dry-run`: planned items count as `ok` in the Done summary (was always `ok=0`).
- 401 re-authentication is limited to **one attempt per request** (no retry loop if the new token is also rejected).

Fixed:

- HLS segment downloads retry when the body disconnects mid-stream and overwrite the partial segment.
- Reauth invalidates the cached session before obtaining a new AccessToken.

Internal:

- Shared helpers for retries/backoff, pagination, download loop, item-id resolution, and optional request kwargs.
- TypedDict shapes for Emby API responses; Ruff lint gate in CI.
- Much stronger automated tests (retry matrix, title resolution, download skip/dry-run, stderr contracts). Editable installs link to `src/` so pytest sees live edits.

## 0.5.1

- Set HTTP `User-Agent` to `emby-cli/<version>` (clear client identity; replaces the default `python-requests` UA).
- `search`: when results are capped by `--count`, print `Total: N (out of M)`.
- README: example tweaks and docs polish.

## 0.5.0

Breaking:

- `show`: `--item` / `--library` require `--id` only (no QUERY / `--search`). Find IDs with `search`, then inspect with `show`.

Added:

- `play --item [QUERY]` (aligned with search/download); `--search` remains an alternative.
- `play --id` accepts a comma-separated list of IDs (same idea as `download --item --id`).
- Library name matching unified to substring + disambiguation for `search` / `download` (`match_libraries`); shared `library_rows` counts use `Movie,Episode,Audio`.
- User-facing lists sort by Id descending, then Name alphabetically.

Changed:

- `show`: omit empty/`?` Media fields; library recent list still Movie/Episode/Audio.
- Narrow item-fetch `except` to `RequestException` / `RuntimeError` (plus `OSError` in download I/O).
- Docs: CSV `--id` for download/play; download `-h` authorized-use note.

## 0.4.1

- README rewritten for end users (quick start, everyday workflows, responsible-use disclaimer).

## 0.4.0

Added:

- `show`: detail view for `--item` / `--library` (QUERY or `--id`); multiple matches print a disambiguation table with IDs. Libraries include total item count and the last 10 added (`DateCreated`), limited to Movie/Episode/Audio (no Studio, etc.).
- `search` / `download`: `--item QUERY` / `--library QUERY` (query on the mode flag); `--media-item` is an alias of `--item`. `--search` still works as an alternative selector.

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

Added:

- Credential store: single kubeconfig-style `auth.json` (`contexts` + `current_context`); legacy `*.cache` migrated on first use.
- `login` / `logout` (logout calls `POST /Sessions/Logout` when possible and always clears the local context).
- `emby-cli config`: `current-server`, `get-servers`, `use-server`, `view` (tokens redacted).
- Without `--server` / `EMBY_SERVER`, operational commands use the active context server.
- Selectors for `search` / `download` / `play` validated before authenticating.
- `info`: Connection / Server / Content sections; libraries shown as count only.
- Silent username auth (no `Authenticating…` / `OK`); transparent re-login on HTTP 401 when password is known.

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
