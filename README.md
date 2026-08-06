# emby-cli

[PyPI](https://pypi.org/project/emby-cli/)
[License: CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)

CLI to **list, search, play, and download/backup** original media files from an [Emby](https://emby.media/) server via its REST API. Only HTTP access is required (default port 8096) — no SSH or rsync.

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
| `EMBY_SERVER` | Server URL (required) |
| `EMBY_API_KEY` | API key (or use username/password) |
| `EMBY_USERNAME` / `EMBY_PASSWORD` | Name/password auth |
| `EMBY_OUTPUT` | Download directory (default `./downloads`) |
| `EMBY_METHOD` | `download`, `stream`, or `hls` |
| `EMBY_PLAYER` | External player for `play` |

See `.env.example`. The app does not load `.env` itself — `source` it or export vars.

## Usage

```bash
emby-cli version
emby-cli info
emby-cli list
emby-cli search "Title"
emby-cli search "Title" --count 50
emby-cli download -i <itemId> -o ./downloads
emby-cli sync -l "Movies"
emby-cli batch -F titles.txt -n
emby-cli batch -F titles.txt --pick-best-item
emby-cli play "Movie (2010)"
emby-cli play "Show S01E01" --pick-best-item
```

`info` reports libraries and totals from `GET /Items/Counts` (totals may include multiple versions of the same title).

Title resolution (`play` / `batch`) is **strict** by default (year mismatch or multiple matches fail that line). Pass `--pick-best-item` to auto-select the best ≤1080p version. In `batch`, a season line like `Show S01` downloads the whole season (with the same pick-best rule per episode version).

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
