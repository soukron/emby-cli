# emby-cli

[PyPI](https://pypi.org/project/emby-cli/)
· [License: CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)

Search, browse, play, download media, and manage collections on your [Emby](https://emby.media/) server — from the terminal. Only HTTP access to the server is needed (typically port 8096). No SSH, no shared folders, no rsync.

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

**3. Search and play:**

```bash
emby-cli search --item "matrix"
emby-cli play --item "matrix (1999)" --pick-best-item
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
emby-cli search --item "fast and furious" --count 5
emby-cli search --item "spider-man" --type Movie --year 2017
emby-cli search --item --id 123456
emby-cli search --library "peliculas"
emby-cli search --library --count all
emby-cli search --library --order-by items --desc --count 1
emby-cli search --item "matrix" --order-by resolution --desc --no-cache
```

`--item` and `--library` accept the search text directly. You can also pass `--id` when you already know the Emby ID.

### Show details

Inspect one title or one library by Emby ID (use `search` first if you need to find the ID):

```bash
emby-cli show --item --id 123456
emby-cli show --library --id 614156
emby-cli show --item --id 123456 --no-cache
```

### Collections

Search collections (`BoxSet`) or inspect a collection and all its existing
members. A positional name is a case-insensitive substring; use `--id` when a
name is ambiguous:

```bash
emby-cli collection list
emby-cli collection list --order-by items --desc
emby-cli collection search
emby-cli collection search "star" --order-by year --desc
emby-cli collection show "Star Wars"
emby-cli collection show --id 1234
emby-cli collection download "Star Wars" --dry-run
emby-cli collection download --id 1234 -o ./downloads
emby-cli collection play "Star Wars" --player vlc
emby-cli collection play --id 1234
```

`collection download` resolves the collection and downloads each member
individually via the same item download pipeline as `item download`.

`collection list` is an alias for `collection search --count all` (every
`BoxSet`, no name filter). Use `collection search [QUERY]` when you want to
filter or limit results (`--count` defaults to 30).

Create, rename, and manage Movie members:

```bash
emby-cli collection create "Star Wars" --item 456,789
emby-cli collection rename --id 1234 "Star Wars Saga"
emby-cli collection rename --id 1234 "Star Wars Saga" --short-name "Star Wars 01"
emby-cli collection add-item --id 1234 --item 456,789 --item 101
emby-cli collection remove-item "Star Wars Saga" --item 456,789
```

Update metadata with `collection set` (`KEY=VALUE` assignments). `--id` may
appear before the subcommand:

```bash
emby-cli collection --id 1234 set year=1980
emby-cli collection --id 1234 set name=Peliculas short-name=Pelis
emby-cli collection set "Star Wars" display-order=PremiereDate overview="Saga overview"
```

Supported fields: `year`, `name`, `short-name`, `display-order`
(`PremiereDate` or `SortName`), and `overview`.

`--item` is repeatable and accepts comma-separated IDs. In this first version,
only items whose Emby type is `Movie` can be added or removed. Existing members
of other types, including music, are still displayed by `collection show`.
Invalid, missing, ambiguous, or non-Movie members are reported individually;
valid members in the same command are still processed, and the command exits
non-zero if any member failed.

Deleting is guarded by an interactive confirmation and verifies that the target
is a `BoxSet`. Use `--yes` for deliberate non-interactive use:

```bash
emby-cli collection delete "Star Wars Saga"
emby-cli collection delete --id 1234 --yes
```

Deleting the collection removes the virtual `BoxSet`, not its member media.
Collection mutations require an Emby user or API key with permission to edit
metadata (typically an administrator).

### Libraries

Browse Emby library views (Movies, TV, Music, …). A positional name is a
case-insensitive substring; use `--id` when a name is ambiguous:

```bash
emby-cli library list
emby-cli library list --type movies --order-by items --desc
emby-cli library search
emby-cli library search "pel" --count all
emby-cli library show "Películas"
emby-cli library show --id 614156
emby-cli library --id 614156 show
emby-cli library download "Películas" --dry-run
emby-cli library download --id 614156 -o ./downloads
emby-cli library play "Películas" --player vlc
emby-cli library play --id 614156
```

`library list` is an alias for `library search --count all`. `--type` filters by
library collection type (`movies`, `tvshows`, `music`, …). Detail output matches
`show --library --id`. `library download` resolves the library and downloads
each item individually via the same item download pipeline as `item download`.

Legacy library browsing via `search --library`, `show --library`, and
`download --library` still works.

### Media items

Search movies, episodes, audio, and other playable items. A positional name uses
Emby search; use `--id` when results are ambiguous:

```bash
emby-cli item list
emby-cli item list --type movie --year 1999 --order-by year --desc
emby-cli item search "matrix"
emby-cli item search --type audio --count all
emby-cli item show "The Matrix (1999)"
emby-cli item show --id 123456
emby-cli item --id 123456 show
emby-cli item play "matrix (1999)" --pick-best-item
emby-cli item play --id 123456 --player vlc --wait
emby-cli item download "matrix (1999)" --pick-best-item
emby-cli item download --id 123456 --method stream
```

`item list` is an alias for `item search --count all`. Detail output matches
`show --item --id`. `item play` mirrors `play --item` / `play --id`; `item download`
mirrors `download --item` using the same output/method flags.

Legacy `search --item`, `show --item`, `download --item`, and `play --item` still work.

### Play

Open a title in an external player (VLC, mpv, IINA, …):

```bash
emby-cli item play "matrix (1999)" --pick-best-item
emby-cli play --item "matrix (1999)" --pick-best-item
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
emby-cli item download --id 123456
emby-cli download --item "breaking bad S01E01" --pick-best-item
emby-cli download --library "peliculas 4k"
emby-cli download --from-file titles.txt
```

A comma-separated list of IDs (`a,b,c`) is supported for `download --item --id` and `play --id`. `show` and `search` accept a single `--id` each.

Useful options:


| Option             | Meaning                                           |
| ------------------ | ------------------------------------------------- |
| `-n` / `--dry-run` | Resolve titles only — do not write files          |
| `-o` / `--output`  | Output folder (default `./downloads`)             |
| `-f` / `--force`   | Re-download even if a matching local file exists  |
| `--mirror-path`    | Recreate source subdirectories under the output folder |
| `--path-strip`     | Strip this server path prefix with `--mirror-path` (env: `EMBY_PATH_STRIP`) |
| `--pick-best-item` | When several versions match, pick the best ≤1080p |
| `-m` / `--method`  | Download method                                            |


**Title lines** in `--item` / `--from-file` can look like:

- `Movie (2010)`
- `Show S01E05`
- `Show S01` — whole season

By default, matching is **strict**: a wrong year or several ambiguous results stops with a table of candidates. Add `--pick-best-item` to choose automatically (best quality up to 1080p).

Library downloads match the library **name** (case-insensitive, unique match required).

### Data cache

Read-only commands (`search`, `show`, `play`, `info`, `collection list`,
`collection search`, `collection show`, `library list`, `library search`, and
`library show`, `item list`, `item search`, `item show`, and `item play`) use a JSON disk cache under
`~/.cache/emby-cli/data` (or under `EMBY_CACHE_DIR/data`).

- Default TTL: **600 seconds** (`EMBY_DATA_CACHE_TTL` to override).
- `--no-cache`: do not read cache; call API directly and refresh cache on disk.
- Cache keys are isolated by **server URL + user ID** to prevent cross-server mixing.
- `download` never uses this data cache.
- Collection mutations resolve against fresh server state and invalidate affected
  collection cache entries immediately.

---



## Logging in and switching servers


| Approach         | When to use                                                        |
| ---------------- | ------------------------------------------------------------------ |
| `emby-cli login` | Recommended — saves a session and remembers the server             |
| API key          | `--api-key` / `EMBY_API_KEY` (keys are not stored by `login`)      |
| Flags / env      | `--server`, `--username`, `--password` or `EMBY_*` for one-off use |


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


| Method               | Best for                                |
| -------------------- | --------------------------------------- |
| `download` (default) | Normal file download from Emby          |
| `stream`             | Direct stream URL (similar to Emby Web) |
| `hls`                | HLS remux to `.mkv`                     |


---



## Configuration reference

Flags override environment variables. Optional template: `.env.example` (export the vars yourself — the CLI does not load `.env` files).


| Variable                          | Description                                         |
| --------------------------------- | --------------------------------------------------- |
| `EMBY_SERVER`                     | Server URL                                          |
| `EMBY_API_KEY`                    | API key                                             |
| `EMBY_USERNAME` / `EMBY_PASSWORD` | Username / password                                 |
| `EMBY_OUTPUT`                     | Download directory (default `./downloads`)          |
| `EMBY_METHOD`                     | `download`, `stream`, or `hls`                      |
| `EMBY_PATH_STRIP`                 | Server path prefix to strip with `--mirror-path`      |
| `EMBY_PLAYER`                     | External player command or path                     |
| `EMBY_ITEM_ID`                    | Default `--id` for item download / play             |
| `EMBY_CACHE_DIR`                  | Credentials directory (default `~/.cache/emby-cli`) |
| `EMBY_NO_AUTH_CACHE`              | `1` = disable session cache                         |
| `EMBY_DATA_CACHE_TTL`             | Data-cache TTL in seconds (default `600`)           |


---



## Tips

- Prefer **search → show → download** when you are unsure of the exact title.
- Prefer **IDs** (`--id`) when you already have them — no ambiguity.
- Use `--dry-run` before a large library or file-list download.
- Content totals in `info` can count multiple versions of the same title separately.

---



## For contributors

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check .
python -m build && twine check dist/*
```

Architecture, CLI contracts, testing rules, and release process: see **[AGENTS.md](AGENTS.md)** (for humans and AI agents). Releases: tag `vX.Y.Z` and push — CI publishes to PyPI only (no GitHub Releases).

---



## Responsible use

This tool talks to Emby over its normal HTTP API. Whether download or playback is allowed depends on **how that server is configured** and on **the terms set by whoever runs it**.

Use `emby-cli` only on servers you are authorized to access, and only in ways that comply with that server’s terms of use, policies, and applicable law. The authors provide the software as-is and are **not responsible** for misuse, for downloads from servers that disallow them, or for any consequences of using the tool.

---



## License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — free for non-commercial use.
