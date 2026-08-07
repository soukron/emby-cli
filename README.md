# emby-cli

[PyPI](https://pypi.org/project/emby-cli/)
[License: CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)

CLI to **search, play, and download/backup** original media files from an [Emby](https://emby.media/) server via its REST API. Only HTTP access is required (default port 8096) — no SSH or rsync.

## Install

```bash
pip install emby-cli
```

Development (from a clone of this repo):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

Set environment variables (or pass CLI flags):

| Variable | Description |
|----------|-------------|
| `EMBY_SERVER` | Server URL (required for most commands) |
| `EMBY_API_KEY` | API key (or use username/password) |
| `EMBY_USERNAME` / `EMBY_PASSWORD` | Name/password auth |
| `EMBY_OUTPUT` | Download directory (default `./downloads`) |
| `EMBY_METHOD` | `download`, `stream`, or `hls` |
| `EMBY_PLAYER` | External player for `play` |
| `EMBY_ITEM_ID` | Default for `--id` (item mode / play) |
| `EMBY_CACHE_DIR` | Credentials directory (default `~/.cache/emby-cli`; file `auth.json`) |
| `EMBY_NO_AUTH_CACHE` | Set to `1` to disable reading/writing the AccessToken cache |

See `.env.example`. The app does not load `.env` itself — `source` it or export vars.

With username/password, sessions are stored in a single kubeconfig-style `auth.json` (`contexts` + `current_context`). `emby-cli login` saves a server entry and makes it active. Without `--server`, commands use the active server. Manage entries with `emby-cli config` (`current-server`, `get-servers`, `use-server`, `view`). API keys are not stored.

## Usage

```bash
emby-cli help
emby-cli login
emby-cli logout
emby-cli config get-servers
emby-cli config use-server 'user@http://emby:8096'
emby-cli config current-server
emby-cli config view
emby-cli version
emby-cli info
emby-cli search --item "Title"
emby-cli search --item "Title" --count 50
emby-cli search --item --id 123456
emby-cli search --item --all
emby-cli search --library --all
emby-cli search --library --id 614156
emby-cli search --library "PELICULAS"
emby-cli show --item "Title"
emby-cli show --item --id 123456
emby-cli show --library "PELICULAS"
emby-cli show --library --id 614156

emby-cli download --item --id 123456
emby-cli download --item "californication S01E01" --pick-best-item
emby-cli download --library --id 12345
emby-cli download --library "PELICULAS 4K"
emby-cli download --from-file titles.txt --dry-run

emby-cli play --id 123456
emby-cli play --search "Pelicula (1980)" --pick-best-item
```

`info` reports libraries and totals from `GET /Items/Counts` (totals may include multiple versions of the same title).

Title resolution (`play --search`, `download --item` with a query, `download --from-file`) is **strict** by default (year mismatch or multiple matches fail). Pass `--pick-best-item` to auto-select the best ≤1080p version. With `--from-file` or `--item` + query, a season line like `Show S01` downloads the whole season (same pick-best rule per episode version). Library query requires an exact name match (case-insensitive); no pick-best.

`--dry-run` / `-n` works for all `download` modes (no files written).

Download methods (`-m` / `EMBY_METHOD`):

- `download` — `GET /Items/{id}/Download`
- `stream` — DirectStreamUrl / `original.*` (Emby Web style)
- `hls` — HLS segments remuxed to `.mkv` (needs `static-ffmpeg`)

## Development

```bash
pip install -e ".[dev]"
pytest -q
python -m build && twine check dist/*
```

To publish a release, tag `vX.Y.Z` and push it (or create a GitHub Release). CI builds the package and publishes to PyPI via Trusted Publisher.

## License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)
