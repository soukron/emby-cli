# emby-cli

[PyPI](https://pypi.org/project/emby-cli/)
· [License: CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)

Search, browse, play, and download media from your [Emby](https://emby.media/) server — from the terminal. Only HTTP access to the server is needed (typically port 8096). No SSH, no shared folders, no rsync.

```bash
pip install emby-cli
```

---

## Quick start

**1. Log in once** (username + password, or an API key):

```bash
emby-cli login --server http://emby:8096 --username you
# prompted for password if not set
```

Your session is saved locally. Later commands reuse it, so you usually do not need to pass `--server` again.

**2. Check the connection:**

```bash
emby-cli info
```

**3. Search and download:**

```bash
emby-cli search --item "matrix"
emby-cli download --item "matrix" --pick-best-item
```

Use `emby-cli help` for the command list, and `emby-cli <command> -h` for options.

---

## Everyday use

### Server info

```bash
emby-cli version    # CLI version (and Emby version when connected)
emby-cli info       # user, server, library count, content totals
```

### Search

Find movies, episodes, and other media — or list libraries:

```bash
emby-cli search --item "fast and furious"
emby-cli search --item "fast and furious" --count 50
emby-cli search --item --id 123456
emby-cli search --library "peliculas"
emby-cli search --library --all
```

`--item` and `--library` accept the search text directly. You can also pass `--id` when you already know the Emby ID.

### Show details

Inspect one title or one library by Emby ID (use `search` first if you need to find the ID):

```bash
emby-cli show --item --id 123456
emby-cli show --library --id 614156
```

### Play

Open a title in an external player (VLC, mpv, IINA, …):

```bash
emby-cli play --item "Pelicula (1980)" --pick-best-item
emby-cli play --id 123456
emby-cli play --id 111,222,333
emby-cli play --id 123456 --player vlc --wait
```

Set `EMBY_PLAYER` if the player is not found automatically. A comma-separated list of IDs works for `play --id` and `download --item --id` (not for `show` / `search`).

### Download

Download a single title, a whole library, or a list of titles from a file:

```bash
emby-cli download --item --id 123456
emby-cli download --item --id 111,222,333
emby-cli download --item "californication S01E01" --pick-best-item
emby-cli download --library "PELICULAS 4K"
emby-cli download --from-file titles.txt
```

A comma-separated list of IDs (`a,b,c`) is supported for `download --item --id` and `play --id`. `show` and `search` accept a single `--id` each.

Useful options:

| Option | Meaning |
|--------|---------|
| `-n` / `--dry-run` | Resolve titles only — do not write files |
| `-o` / `--output` | Output folder (default `./downloads`) |
| `-f` / `--force` | Re-download even if a matching local file exists |
| `--pick-best-item` | When several versions match, pick the best ≤1080p |
| `-m download\|stream\|hls` | How to fetch the file (see below) |

**Title lines** in `--item` / `--from-file` can look like:

- `Movie (2010)`
- `Show S01E05`
- `Show S01` — whole season (with `--item` or `--from-file`)

By default, matching is **strict**: a wrong year or several ambiguous results stops with a table of candidates. Add `--pick-best-item` to choose automatically (best quality up to 1080p).

Library downloads match the library **name** (case-insensitive, unique match required).

---

## Logging in and switching servers

| Approach | When to use |
|----------|-------------|
| `emby-cli login` | Recommended — saves a session and remembers the server |
| API key | `--api-key` / `EMBY_API_KEY` (keys are not stored by `login`) |
| Flags / env | `--server`, `--username`, `--password` or `EMBY_*` for one-off use |

Manage saved servers:

```bash
emby-cli config get-servers
emby-cli config current-server
emby-cli config use-server 'you@http://emby:8096'
emby-cli config view          # tokens redacted
emby-cli logout               # revoke and forget the current session
```

Sessions live under `~/.cache/emby-cli/auth.json` (override with `EMBY_CACHE_DIR`). Set `EMBY_NO_AUTH_CACHE=1` to never read or write the cache.

---

## Download methods

Choose with `-m` / `EMBY_METHOD`:

| Method | Best for |
|--------|----------|
| `download` (default) | Normal file download from Emby |
| `stream` | Direct stream URL (similar to Emby Web) |
| `hls` | HLS remux to `.mkv` |

---

## Configuration reference

Flags override environment variables. Optional template: `.env.example` (export the vars yourself — the CLI does not load `.env` files).

| Variable | Description |
|----------|-------------|
| `EMBY_SERVER` | Server URL |
| `EMBY_API_KEY` | API key |
| `EMBY_USERNAME` / `EMBY_PASSWORD` | Username / password |
| `EMBY_OUTPUT` | Download directory (default `./downloads`) |
| `EMBY_METHOD` | `download`, `stream`, or `hls` |
| `EMBY_PLAYER` | External player command or path |
| `EMBY_ITEM_ID` | Default `--id` for item download / play |
| `EMBY_CACHE_DIR` | Credentials directory (default `~/.cache/emby-cli`) |
| `EMBY_NO_AUTH_CACHE` | `1` = disable session cache |

---

## Tips

- Prefer **search → show → download** when you are unsure of the exact title.
- Prefer **IDs** (`--id`) when you already have them — no ambiguity.
- Use **`--dry-run`** before a large library or file-list download.
- Content totals in `info` can count multiple versions of the same title separately.

---

## Responsible use

This tool talks to Emby over its normal HTTP API. Whether download or playback is allowed depends on **how that server is configured** and on **the terms set by whoever runs it**.

Use `emby-cli` only on servers you are authorized to access, and only in ways that comply with that server’s terms of use, policies, and applicable law. The authors provide the software as-is and are **not responsible** for misuse, for downloads from servers that disallow them, or for any consequences of using the tool.

---

## For contributors

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
python -m build && twine check dist/*
```

Releases: tag `vX.Y.Z` and push (or create a GitHub Release). CI publishes to PyPI via Trusted Publisher.

## License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — free for non-commercial use.
