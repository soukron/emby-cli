# Changelog

## Unreleased

### Added

- `--parse-query` on `item search` and `item show` to interpret title-line syntax
  (`Movie (1999)`, `Show S01E01`). Default is strict Emby `SearchTerm` search.
- `--no-parse-query` on `item play` and `item download` to resolve QUERY via Emby
  search instead of title-line parsing (default: parse for play/download).
- `Series` column in item search tables when results include episodes.
- `--order-by added-date` for sorting by library add date (`DateCreated`).

### Changed

- `item search`, `item list`, and `item show` no longer parse QUERY by default;
  use `--parse-query` for structured title lines or `--year` to narrow results.
- Strict catalog search filters by display name after Emby recall (phrase match for
  multi-word queries; episode codes like `S01E01` must prefix the display name).
- Renamed item `--order-by added` to `added-date`.

## 0.7.0

Added:

- `collection search` and `collection show` for paginated `BoxSet` discovery,
  name/ID resolution, metadata, and generic member listings.
- `collection list` as an obvious alias for `collection search --count all`.
- `collection create`, `rename`, `add-item`, `remove-item`, and guarded `delete`
  operations. Delete requires interactive confirmation unless `--yes` is passed.
- Repeatable/CSV `--item` values for collection membership. `create --type`
  selects the expected member type (`movie` default, `audio`/`music`, etc.).
- `collection rename --short-name` to update Emby's `SortName` together with
  `Name`.
- `collection set KEY=VALUE …` to update collection metadata (`year`,
  `name`, `short-name`, `display-order`, `overview`). Parent-level
  `--id` is supported before the subcommand.
- `ItemsService.merge_and_update()` for safe GET→merge→POST metadata edits.
- `library list`, `library search`, and `library show` for read-only library view
  discovery and inspection (`/Users/{uid}/Views`). `library list` is an alias for
  `library search --count all`. Supports `--type`, `--order-by`, and parent/subcommand
  `--id` like collections. Legacy `search --library` / `show --library` are
  deprecated wrappers.
- `item list`, `item search`, and `item show` for read-only media discovery and
  inspection via `ItemsService.search()`. `item list` is an alias for
  `item search --count all`. Supports `--type`, `--year`, `--order-by`, and
  parent/subcommand `--id`. Legacy `search --item` / `show --item` are
  deprecated wrappers.
- `item download`, `library download`, and `collection download` for bulk and
  single-item downloads via shared `item_ops` helpers. Library and collection
  downloads write into `output/<name>/`; items use flat filenames by default.
  `item download --from-file` replaces legacy `download --from-file`.
- `--mirror-path` and `EMBY_PATH_STRIP` / `--path-strip` to recreate server
  subdirectories under the output folder when needed.
- `library play` and `collection play` to launch an external player for every
  playable item in a library view or collection, with optional `--order-by`.
- Legacy top-level `download` remains as a thin wrapper over the new helpers.

Deprecated:

- Top-level `search`, `show`, `play`, and `download` emit a stderr warning and
  remain as compatibility wrappers. Prefer `item`, `library`, and `collection`
  subcommands instead. `item download --from-file` replaces `download --from-file`;
  `item play` / `item download` now use strict title resolution for QUERY lines
  (same as the legacy commands).

Changed:

- `collection create` / `add-item` / `remove-item`: `create --type` selects the
  expected member Emby type (`movie` default, `audio`/`music`, `episode`/`tv`,
  `video`). `add-item` / `remove-item` accept any supported member type without
  `--type`. `create` skips the API call when every `--item` fails validation.
- `item list` / `item search`: `--order-by` adds `release-date` (`PremiereDate`),
  `added` (`DateCreated`), `resolution` (`Resolution,SortName`), and `size`
  (`Size,SortName`, same as Emby Web for movies). Legacy `search --item` unchanged.
- `library play` and `collection play`: optional `--order-by` / `--desc` using the
  same item sort keys (`year`, `name`, `id`, `release-date`, `added`, `resolution`, `size`).
- Download orchestration, skip logic, and item loops now live in `item_ops.py`;
  `library play` / `collection play` list members via the same
  `ItemListingQuery` + `fetch_item_listing()` path as `item list/search`
  (scoped with `parent_id`).
  `download_ops.py` retains library name/id matching only.
- `EmbyClient` now composes entity-oriented `ItemsService`,
  `CollectionsService`, and `LibrariesService` modules while retaining one shared HTTP/auth/retry/cache
  transport. `ItemsService.search()` adds v2 catalog search keys for the new
  `item` commands; legacy browse helpers remain on `EmbyClient`.
- Metadata cache now supports exact invalidation. Collection mutations bypass
  stale reads and invalidate catalog, detail, and member entries immediately.
- Operational HTTP 403 responses from collection commands produce a concise
  metadata-permission error instead of a traceback.

Safety:

- Collection creation is not retried after a server error, avoiding uncertain
  duplicate creation.
- Collection deletion verifies `Type=BoxSet` before calling Emby's generic item
  deletion endpoint; member deletion endpoints are never called.

## 0.6.1

Fixed:

- `tests/test_search.py`: normalize imports so Ruff passes consistently in CI and local `make lint`.

Changed:

- Release process docs: require running `make lint` and `make test` before creating/pushing a version tag.
- CI/CD hardening: run CI on `v*` tags, and run Ruff + pytest inside `publish.yml` before building/publishing to PyPI.

## 0.6.0

Changed:

- `search`: removed `--all`; use `--count all` to list everything.
- `search --item`: always fetch all paginated results (`limit=None`), then apply `--type` and `--year`, then apply `--count`.
- `search`: `--order-by` now supports `name`, `id`, `year`, `size`, `resolution`, and `items` (`items` for libraries).
- `search --library`: QUERY is optional; without QUERY it lists all libraries and then applies `--order-by`/`--count`.

Added:

- Data cache under `~/.cache/emby-cli/data` for read-only metadata calls in `search`, `show`, `play`, and `info` (default TTL: 600s; env: `EMBY_DATA_CACHE_TTL`).
- `--no-cache` for `search`, `show`, `play`, and `info`: bypass disk-cache reads, fetch from API, and refresh cache on disk.

## 0.5.4

Fixed:

- macOS: suppress urllib3 `NotOpenSSLWarning` (system Python + LibreSSL) by filtering before `requests` is imported — the previous filter in `cli.py` ran too late because `__init__.py` already pulled in urllib3.

## 0.5.3

Fixed:

- Expired/revoked sessions: print a clear `error:` on stderr (suggest `emby-cli login`) instead of an `HTTPError` traceback; drop the stale AccessToken from the local cache.

Docs:

- Public `AGENTS.md` for contributors (layout, auth, CLI contracts, tests, release).

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
