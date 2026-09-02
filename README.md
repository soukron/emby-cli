# emby-cli

[PyPI](https://pypi.org/project/emby-cli/)
· [License: CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)

Search, browse, play, and download media from an [Emby](https://emby.media/)
server without leaving the terminal. You only need HTTP access to Emby (usually
port 8096): no SSH, shared folders, or rsync.

```bash
pip install emby-cli

# Or, install in an isolated environment (recommended)
pipx install emby-cli    # with pipx
uv tool install emby-cli # with uv (faster)
```

## Start in 60 seconds

```bash
# Log in once; the saved session is reused by later commands
emby-cli login --server http://emby:8096 --username you

# Check the connection, find a title, and play it
emby-cli info
emby-cli item search "matrix"
emby-cli item play "matrix (1999)" --pick-best-item
```

Run `emby-cli help` for the command list or `emby-cli <command> -h` for the
options of a command.

## The command model

Commands are grouped by what you want to work with:

| Scope | Browse | Inspect | Play or download |
| --- | --- | --- | --- |
| Media | `item list`, `item search` | `item show` | `item play`, `item download` |
| Libraries | `library list`, `library search` | `library show` | `library play`, `library download` |
| Collections | `collection list`, `collection search` | `collection show` | `collection play`, `collection download` |

Most commands accept either a readable query or an exact Emby ID:

```bash
emby-cli item show "The Matrix (1999)" --parse-query
emby-cli item show --id 123456
```

Use a query while exploring and switch to `--id` when you need an unambiguous,
repeatable command. `item play --id` and `item download --id` also accept a
comma-separated list such as `--id 111,222,333`.

`list` returns all results. `search [QUERY]` defaults to 30 and can be adjusted
with `--count`; use `--count all` to remove the limit.

## Common workflows

### Find, inspect, and play

```bash
# Narrow the search
emby-cli item search "spider-man" --type movie --year 2017

# Inspect the result, then open it in your preferred player
emby-cli item show --id 123456
emby-cli item play --id 123456 --player vlc --wait
```

Item queries use strict name matching after Emby returns candidates. Structured
queries are opt-in when searching and showing:

```bash
emby-cli item search "Matrix (1999)" --parse-query
emby-cli item search "Californication S01E01" --parse-query
```

`item play` and `item download` understand structured title lines by default.
Use `--no-parse-query` when parentheses or episode-like text are part of the
literal title. If several versions match, `--pick-best-item` chooses the best
quality up to 1080p.

Set `EMBY_PLAYER` if your player is not detected automatically.

### Download with confidence

Preview a large operation first, then choose a destination:

```bash
emby-cli item download "breaking bad S01E01" --dry-run
emby-cli item download --id 123456 --output ./downloads
emby-cli item download --id 123456 --pick-best-item   # series: one file per SxxExx
emby-cli item download --from-file titles.txt --dry-run
emby-cli library download "peliculas 4k" --output ./downloads
```

Lines passed as a query or read from `--from-file` may describe a movie, an
episode, or a complete season:

```text
Movie (2010)
Show S01E05
Show S01
```

Useful download options:

| Option | Purpose |
| --- | --- |
| `-n`, `--dry-run` | Resolve titles without writing files |
| `-o`, `--output` | Choose the output folder (default: `./downloads`) |
| `-f`, `--force` | Replace a matching local file |
| `--mirror-path` | Recreate source subdirectories under the output folder |
| `--path-strip` | Remove a server path prefix when mirroring |
| `--pick-best-item` | Resolve multiple versions automatically |
| `-m`, `--method` | Select `download`, `stream`, or `hls` |

A wrong year or an ambiguous match stops and displays the candidates instead of
guessing. Library downloads also require a unique, case-insensitive name match.

### Browse a library

```bash
emby-cli library list --type movies --order-by items --desc
emby-cli library search "pel" --count all
emby-cli library show "Películas"
emby-cli library play --id 614156
```

Library names use case-insensitive substring matching. Use `--id` when two
libraries have similar names. `--type` accepts Emby collection types such as
`movies`, `tvshows`, and `music`.

### Build and manage a collection

```bash
# Discover and inspect collections
emby-cli collection list --order-by items --desc
emby-cli collection show "Star Wars"

# Create one, add media, and edit its metadata
emby-cli collection create "Star Wars" --item 456,789
emby-cli collection add-item --id 1234 --item 101
emby-cli collection set --id 1234 year=1980 display-order=PremiereDate

# Use it like any other group of media
emby-cli collection play --id 1234
emby-cli collection download --id 1234 --dry-run
```

Other mutations are `rename`, `remove-item`, and `delete`. `--item` is
repeatable and accepts comma-separated IDs. `collection set` supports `year`,
`name`, `short-name`, `display-order` (`PremiereDate` or `SortName`), and
`overview`.

Creation defaults to movie members. Use `collection create --type audio`,
`--type episode`, or `--type video` for other media; adding and removing members
does not need `--type`.

Deletion asks for confirmation and verifies that the target is a `BoxSet`:

```bash
emby-cli collection delete "Star Wars"
emby-cli collection delete --id 1234 --yes  # deliberate non-interactive use
```

This removes the virtual collection, not its media. Collection changes require
an Emby account or API key allowed to edit metadata, usually an administrator.

## Login and saved servers

`emby-cli login` is the simplest option: it saves a session and remembers the
server. API keys and one-off credentials can instead be supplied through flags
or environment variables.

```bash
emby-cli config get-servers
emby-cli config current-server
emby-cli config use-server 'you@http://emby:8096'
emby-cli config rename-server 'you@http://emby:8096' --new-name synology
emby-cli config use-server synology   # alias from rename-server
emby-cli config view          # tokens are redacted
emby-cli logout               # revoke and forget the current session
```

Sessions are stored in `~/.cache/emby-cli/auth.json`; change the base directory
with `EMBY_CACHE_DIR`. Set `EMBY_NO_AUTH_CACHE=1` to disable session storage.

## Downloads, cache, and configuration

Choose a download method with `--method` or `EMBY_METHOD`:

| Method | Result |
| --- | --- |
| `download` (default) | Normal file download from Emby |
| `stream` | Direct stream URL, similar to Emby Web |
| `hls` | HLS remux to `.mkv` |

Read-only commands use a JSON disk cache under `~/.cache/emby-cli/data` (or
`EMBY_CACHE_DIR/data`). Its default TTL is 600 seconds. Pass `--no-cache` to
bypass the cached value and refresh it from Emby. Cache entries are isolated by
server URL and user ID; downloads and collection mutations always use fresh
server state.

Flags override environment variables. The optional [`.env.example`](.env.example)
is a template only—the CLI does not load `.env` files itself.

| Variable | Purpose |
| --- | --- |
| `EMBY_SERVER` | Server URL |
| `EMBY_API_KEY` | API key |
| `EMBY_USERNAME`, `EMBY_PASSWORD` | Login credentials |
| `EMBY_OUTPUT` | Download directory |
| `EMBY_METHOD` | `download`, `stream`, or `hls` |
| `EMBY_PATH_STRIP` | Server prefix removed by `--mirror-path` |
| `EMBY_PLAYER` | External player command or path |
| `EMBY_CACHE_DIR` | Base directory for credentials and data cache |
| `EMBY_NO_AUTH_CACHE` | Set to `1` to disable the session cache |
| `EMBY_DATA_CACHE_TTL` | Data-cache TTL in seconds |

## For contributors

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check .
python -m build && twine check dist/*
```

Architecture, CLI contracts, testing rules, and the release process are in
**[AGENTS.md](AGENTS.md)**. Releases are published to PyPI by pushing a
`vX.Y.Z` tag. Standalone binaries for macOS, Linux, and Windows are also
available on the [GitHub Releases](https://github.com/soukron/emby-cli/releases)
page.

## Responsible use

This tool talks to Emby over its normal HTTP API. Whether download or playback
is allowed depends on **how that server is configured** and on **the terms set
by whoever runs it**.

Use `emby-cli` only on servers you are authorized to access, and only in ways
that comply with that server’s terms of use, policies, and applicable law. The
authors provide the software as-is and are **not responsible** for misuse, for
downloads from servers that disallow them, or for any consequences of using the
tool.

## License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — free for
non-commercial use.
