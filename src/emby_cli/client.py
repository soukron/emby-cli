"""Emby REST API client: auth, browse, download, stream, HLS."""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import m3u8
import requests
from tqdm import tqdm

from emby_cli.auth_cache import (
    AuthCacheEntry,
    clear_auth_cache,
    load_auth_cache,
    save_auth_cache,
)
from emby_cli.constants import (
    CLIENT_NAME,
    DEFAULT_CHUNK,
    DEVICE_NAME,
    INFO_RETRIES,
    INFO_TIMEOUT,
    ITEM_FIELDS,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
)
from emby_cli.util import remux_segments
from emby_cli.version import get_version

_DEVICE_ID = hashlib.md5(CLIENT_NAME.encode()).hexdigest()
_AUTH_PATH = "/Users/AuthenticateByName"


class _RetryImmediately(Exception):
    """Internal signal for a retry that does not need backoff."""


class _DownloadAlreadyComplete(Exception):
    """Internal signal used when a partial download is already complete."""


def _retry_response(
    request: Callable[[], requests.Response],
    *,
    max_attempts: int,
    connection_message: Callable[[int, int, Exception], str],
    server_message: Callable[[int, int, int], str],
    retry_http_error: Callable[[requests.Response | None], bool] | None = None,
    before_status: Callable[[requests.Response], bool] | None = None,
) -> requests.Response:
    """Run a request with exponential retry for connection and 5xx errors."""
    attempt = 1
    while True:
        response: requests.Response | None = None
        try:
            response = request()
            if before_status is not None and before_status(response):
                raise _RetryImmediately
            response.raise_for_status()
            return response
        except _RetryImmediately:
            if attempt >= max_attempts:
                raise RuntimeError("Request could not be resumed after retries")
            attempt += 1
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt >= max_attempts:
                raise
            wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            print(connection_message(attempt, max_attempts, exc))
            time.sleep(wait)
            attempt += 1
        except requests.HTTPError:
            if retry_http_error is not None and retry_http_error(response):
                continue
            if response is not None and response.status_code >= 500 and attempt < max_attempts:
                wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                print(server_message(response.status_code, attempt, max_attempts))
                time.sleep(wait)
                attempt += 1
                continue
            raise


def _client_version() -> str:
    ver = get_version()
    return ver if ver and ver != "unknown" else "0.0.0"


class EmbyClient:
    def __init__(
        self,
        server_url: str,
        api_key: str | None = None,
        *,
        use_auth_cache: bool = True,
    ):
        base = server_url.rstrip("/")
        if base.lower().endswith("/emby"):
            base = base[: -len("/emby")]
        self.server_url = base.rstrip("/")
        self.api_key = api_key
        self.user_id: str | None = None
        self.access_token: str | None = api_key
        self.use_auth_cache = use_auth_cache
        self._username: str | None = None
        self._password: str | None = None
        self._reauth_attempted = False
        self.session = requests.Session()
        ver = _client_version()
        self.session.headers.update({
            "User-Agent": f"{CLIENT_NAME}/{ver}",
            "X-Emby-Client": CLIENT_NAME,
            "X-Emby-Device-Name": DEVICE_NAME,
            "X-Emby-Device-Id": _DEVICE_ID,
            "X-Emby-Client-Version": ver,
        })

    # -- helpers -------------------------------------------------------------

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        if path.lower().startswith("/emby/"):
            return f"{self.server_url}{path}"
        return f"{self.server_url}/emby{path}"

    def _auth_header(self) -> dict:
        parts = [
            f'MediaBrowser Client="{CLIENT_NAME}"',
            f'Device="{DEVICE_NAME}"',
            f'DeviceId="{_DEVICE_ID}"',
            f'Version="{_client_version()}"',
        ]
        if self.access_token:
            parts.append(f'Token="{self.access_token}"')
        return {"X-Emby-Authorization": ", ".join(parts)}

    @staticmethod
    def _opt_kwargs(
        timeout: float | None = None,
        retries: int | None = None,
    ) -> dict:
        """Return only request options explicitly supplied by the caller."""
        return {
            key: value
            for key, value in (("timeout", timeout), ("retries", retries))
            if value is not None
        }

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        retries: int | None = None,
        **kwargs,
    ) -> requests.Response:
        url = self._url(path)
        max_attempts = MAX_RETRIES if retries is None else max(1, retries)

        def request() -> requests.Response:
            headers = dict(kwargs.get("headers") or {})
            headers.update(self._auth_header())
            return self.session.request(method, url, **{**kwargs, "headers": headers})

        return _retry_response(
            request,
            max_attempts=max_attempts,
            connection_message=lambda attempt, total, exc: (
                f"  Connection error (attempt {attempt}/{total}), retrying in "
                f"{RETRY_BACKOFF_BASE * (2 ** (attempt - 1))}s: {exc}"
            ),
            server_message=lambda status, attempt, total: (
                f"  Server error {status} (attempt {attempt}/{total}), retrying in "
                f"{RETRY_BACKOFF_BASE * (2 ** (attempt - 1))}s"
            ),
            retry_http_error=lambda response: bool(
                response is not None
                and response.status_code == 401
                and path != _AUTH_PATH
                and self._try_reauthenticate()
            ),
        )

    def _get(
        self,
        path: str,
        params: dict | None = None,
        *,
        retries: int | None = None,
        **kwargs,
    ) -> requests.Response:
        return self._request_with_retry("GET", path, params=params, retries=retries, **kwargs)

    def _post(
        self,
        path: str,
        payload: dict | None = None,
        *,
        retries: int | None = None,
        **kwargs,
    ) -> requests.Response:
        return self._request_with_retry("POST", path, json=payload, retries=retries, **kwargs)

    @staticmethod
    def _ensure_api_key(url: str, token: str | None) -> str:
        """Append api_key= to *url* when missing (for external players / HLS)."""
        if not token:
            return url
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        keys = {k.lower() for k in qs}
        if "api_key" in keys or "apikey" in keys:
            return url
        q = dict(qs)
        # flatten single-value lists for urlencode
        flat = {k: v[0] if len(v) == 1 else v for k, v in q.items()}
        flat["api_key"] = token
        return urlunparse(parsed._replace(query=urlencode(flat, doseq=True)))

    # -- auth ----------------------------------------------------------------

    def authenticate(
        self,
        username: str,
        password: str,
        *,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> dict:
        """Authenticate by name. Returns the Emby ``User`` object from the response."""
        data = {"Username": username, "Pw": password}
        resp = self._post(_AUTH_PATH, data, **self._opt_kwargs(timeout, retries))
        body = resp.json()
        try:
            self.access_token = body["AccessToken"]
            user = body["User"]
            self.user_id = user["Id"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                "Authentication response missing AccessToken or User.Id"
            ) from exc
        self._username = username
        self._password = password
        self._reauth_attempted = False
        self._persist_auth_cache()
        return user

    def ensure_user_session(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        force: bool = False,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> dict | None:
        """Restore a cached AccessToken or authenticate.

        When *force* is True (``login``), always calls AuthenticateByName.
        Returns the Emby ``User`` dict from a fresh login, or ``None`` when
        the session was restored from cache.

        *password* ``None`` means unknown (no 401 re-auth); ``""`` is valid.
        """
        if password is not None:
            self._password = password
        if username is not None:
            self._username = username

        if not force and self._try_restore_auth_cache(username):
            return None

        if not username:
            raise RuntimeError(
                "No cached session; provide --username / EMBY_USERNAME "
                "or run `emby-cli login`"
            )
        return self.authenticate(
            username,
            password if password is not None else "",
            timeout=timeout,
            retries=retries,
        )

    def _try_restore_auth_cache(self, username: str | None = None) -> bool:
        if not self.use_auth_cache or self.api_key:
            return False
        entry = load_auth_cache(server_url=self.server_url, username=username)
        if entry is None:
            return False
        self.access_token = entry.access_token
        self.user_id = entry.user_id
        self._username = entry.username
        self._reauth_attempted = False
        return True

    def _persist_auth_cache(self) -> None:
        if not self.use_auth_cache or self.api_key:
            return
        if not self._username or not self.access_token or not self.user_id:
            return
        save_auth_cache(
            AuthCacheEntry.create(
                server_url=self.server_url,
                username=self._username,
                access_token=self.access_token,
                user_id=self.user_id,
            )
        )

    def _invalidate_cached_session(self) -> None:
        if self._username:
            clear_auth_cache(server_url=self.server_url, username=self._username)
        self.access_token = self.api_key
        self.user_id = None

    def _try_reauthenticate(self) -> bool:
        if self._reauth_attempted:
            return False
        if self._username is None or self._password is None:
            return False
        self._reauth_attempted = True
        self._invalidate_cached_session()
        self.authenticate(self._username, self._password)
        return True

    def logout_session(self) -> None:
        """Revoke the current AccessToken via ``POST /Sessions/Logout``.

        Raises on network/HTTP errors other than already-unauthorized.
        Does not clear the on-disk cache — callers should do that.
        """
        if not self.access_token:
            raise RuntimeError("No access token to revoke")
        try:
            self._post("/Sessions/Logout", retries=1)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code in (401, 403):
                return
            raise

    def resolve_user_id(self) -> str:
        if self.user_id:
            return self.user_id
        # Prefer current user bound to the token / API key
        try:
            me = self.get_current_user()
            uid = me.get("Id")
            if uid:
                self.user_id = uid
                return self.user_id
        except requests.HTTPError:
            pass
        users = self._get("/Users").json()
        if not users:
            raise RuntimeError("No users found on server")
        self.user_id = users[0]["Id"]
        return self.user_id

    # -- system --------------------------------------------------------------

    def get_system_info(
        self,
        *,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> dict:
        """Authenticated server info (``GET /System/Info``).

        Full details often require an admin / API-key context; non-admin
        users may get HTTP 401/403 — prefer :meth:`get_system_info_public`
        as a fallback.
        """
        return self._get("/System/Info", **self._opt_kwargs(timeout, retries)).json()

    def get_system_info_public(
        self,
        *,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> dict:
        """Public server info (``GET /System/Info/Public``): name, version, addresses."""
        return self._get(
            "/System/Info/Public", **self._opt_kwargs(timeout, retries)
        ).json()

    def get_current_user(
        self,
        *,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> dict:
        """Current user (``GET /Users/Me``, with fallbacks).

        Some Emby builds return HTTP 500 on ``/Users/Me`` ("Guid should
        contain…dashes"). Fall back to ``/Users/{user_id}`` when known, else
        the first entry from ``GET /Users``.
        """
        kwargs = self._opt_kwargs(timeout, retries)
        try:
            return self._get("/Users/Me", **kwargs).json()
        except requests.HTTPError:
            pass
        uid = self.user_id
        if not uid:
            users = self._get("/Users", **kwargs).json()
            if not users:
                raise RuntimeError("No users found on server")
            uid = users[0]["Id"]
            self.user_id = uid
        return self._get(f"/Users/{uid}", **kwargs).json()

    def probe_session(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> tuple[dict, dict]:
        """One-shot auth + current user + system info (no retries).

        Uses cached AccessToken when possible; otherwise AuthenticateByName
        when *username* is set (or cache miss with credentials). Tries
        ``/System/Info`` then ``/System/Info/Public``.
        """
        kwargs = {"timeout": INFO_TIMEOUT, "retries": INFO_RETRIES}
        user: dict | None = None
        if username is not None or (not self.api_key and self.use_auth_cache):
            restored = self.ensure_user_session(
                username,
                password,
                timeout=INFO_TIMEOUT,
                retries=INFO_RETRIES,
            )
            if restored is not None:
                user = restored
        if user is None:
            user = self.get_current_user(**kwargs)
        elif not user.get("Id") and self.user_id:
            user = self.get_current_user(**kwargs)
        try:
            info = self.get_system_info(**kwargs)
        except requests.HTTPError:
            try:
                info = self.get_system_info_public(**kwargs)
            except requests.HTTPError:
                info = {}
        return user, info

    def get_item_counts(
        self,
        user_id: str | None = None,
        *,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> dict:
        """Aggregate library counts (``GET /Items/Counts``)."""
        params: dict = {}
        if user_id:
            params["UserId"] = user_id
        return self._get(
            "/Items/Counts", params=params or None, **self._opt_kwargs(timeout, retries)
        ).json()

    # -- browse --------------------------------------------------------------

    def get_libraries(
        self,
        *,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> list[dict]:
        uid = self.resolve_user_id()
        resp = self._get(f"/Users/{uid}/Views", **self._opt_kwargs(timeout, retries))
        return resp.json().get("Items", [])

    def get_items(
        self,
        parent_id: str | None = None,
        item_type: str | None = None,
        recursive: bool = True,
        start: int = 0,
        limit: int = 200,
        *,
        sort_by: str = "SortName",
        sort_order: str = "Ascending",
        fields: str | None = None,
    ) -> dict:
        uid = self.resolve_user_id()
        params: dict = {
            "StartIndex": start,
            "Limit": limit,
            "Recursive": str(recursive).lower(),
            "Fields": fields or ITEM_FIELDS,
            "SortBy": sort_by,
            "SortOrder": sort_order,
        }
        if parent_id:
            params["ParentId"] = parent_id
        if item_type:
            params["IncludeItemTypes"] = item_type
        resp = self._get(f"/Users/{uid}/Items", params=params)
        return resp.json()

    def _paginate(
        self,
        path: str,
        params: dict,
        *,
        limit: int | None = None,
        page_size: int = 200,
    ) -> tuple[list[dict], int]:
        """Fetch all Emby result pages, optionally capped to *limit* items."""
        items: list[dict] = []
        start = 0
        total = 0
        while True:
            if limit is not None:
                remaining = limit - len(items)
                if remaining <= 0:
                    break
                batch = min(page_size, remaining)
            else:
                batch = page_size

            page_params = {**params, "StartIndex": start, "Limit": batch}
            page = self._get(path, params=page_params).json()
            chunk = page.get("Items", [])
            items.extend(chunk)
            total = int(page.get("TotalRecordCount", len(items)))
            start += len(chunk)
            if not chunk or start >= total:
                break

        return (items[:limit] if limit is not None else items), total

    def get_all_items(
        self,
        parent_id: str | None = None,
        item_type: str | None = None,
    ) -> list[dict]:
        """Page through all items and return the full list."""
        uid = self.resolve_user_id()
        params: dict = {
            "Recursive": "true",
            "Fields": ITEM_FIELDS,
            "SortBy": "SortName",
            "SortOrder": "Ascending",
        }
        if parent_id:
            params["ParentId"] = parent_id
        if item_type:
            params["IncludeItemTypes"] = item_type
        items, _total = self._paginate(f"/Users/{uid}/Items", params)
        return items

    def get_item_info(self, item_id: str, *, fields: str | None = None) -> dict:
        uid = self.resolve_user_id()
        resp = self._get(
            f"/Users/{uid}/Items/{item_id}",
            params={"Fields": fields or ITEM_FIELDS},
        )
        return resp.json()

    def search_items(
        self,
        query: str,
        item_types: str = "Movie",
        limit: int | None = 25,
    ) -> list[dict]:
        """Search items by name.

        *limit* caps how many items to return. ``None`` fetches all pages
        (Emby ``TotalRecordCount``). Internal callers (resolve) keep the
        default of 25; the CLI ``search --count`` overrides this.
        """
        items, _total = self.search_items_result(
            query, item_types=item_types, limit=limit,
        )
        return items

    def search_items_result(
        self,
        query: str,
        item_types: str = "Movie",
        limit: int | None = 25,
    ) -> tuple[list[dict], int]:
        """Like :meth:`search_items`, but also return Emby ``TotalRecordCount``."""
        uid = self.resolve_user_id()
        return self._paginate(
            f"/Users/{uid}/Items",
            {
                "SearchTerm": query,
                "Recursive": "true",
                "Fields": ITEM_FIELDS,
                "IncludeItemTypes": item_types,
            },
            limit=limit,
        )

    def get_show_episodes(self, series_id: str, season: int | None = None) -> list[dict]:
        uid = self.resolve_user_id()
        params: dict = {"UserId": uid, "Fields": ITEM_FIELDS}
        if season is not None:
            params["Season"] = season
        items, _total = self._paginate(f"/Shows/{series_id}/Episodes", params)
        return items

    # -- playback ------------------------------------------------------------

    def get_playback_info(
        self,
        item_id: str,
        media_source_id: str | None = None,
        max_bitrate: int = 120_000_000,
    ) -> dict:
        """Ask the server how this client should play *item_id* (like Emby Web)."""
        uid = self.resolve_user_id()
        params: dict = {
            "UserId": uid,
            "StartTimeTicks": 0,
            "IsPlayback": "true",
            "AutoOpenLiveStream": "true",
            "MaxStreamingBitrate": max_bitrate,
        }
        if media_source_id:
            params["MediaSourceId"] = media_source_id
        resp = self._request_with_retry(
            "POST",
            f"/Items/{item_id}/PlaybackInfo",
            params=params,
            json={},
        )
        return resp.json()

    def resolve_direct_stream_url(self, item_id: str) -> str:
        """Return an absolute DirectStreamUrl (browser-style original.* stream)."""
        item_info = self.get_item_info(item_id)
        sources = item_info.get("MediaSources") or []
        media_source_id = sources[0]["Id"] if sources else None
        container = (sources[0].get("Container") if sources else None) or "mp4"

        info = self.get_playback_info(item_id, media_source_id=media_source_id)
        play_session_id = info.get("PlaySessionId")
        pb_sources = info.get("MediaSources") or []
        source = pb_sources[0] if pb_sources else {}

        direct = source.get("DirectStreamUrl")
        if not direct:
            if not source.get("SupportsDirectStream", True):
                raise RuntimeError(
                    f"Item {item_id} has no DirectStreamUrl "
                    f"(SupportsTranscoding={source.get('SupportsTranscoding')}). "
                    "Try --method download or --method hls."
                )
            qs = {
                "DeviceId": _DEVICE_ID,
                "MediaSourceId": source.get("Id") or media_source_id or item_id,
                "PlaySessionId": play_session_id
                or hashlib.md5(f"stream-{item_id}-{time.time()}".encode()).hexdigest(),
            }
            if self.access_token:
                qs["api_key"] = self.access_token
            direct = f"/Videos/{item_id}/original.{container}?{urlencode(qs)}"

        return self._ensure_api_key(self._url(direct), self.access_token)

    # -- download ------------------------------------------------------------

    def _download_from_url(
        self,
        url: str,
        dest_path: Path,
        chunk_size: int = DEFAULT_CHUNK,
        resume: bool = True,
        rate_bps: float | None = None,
        expected_size: int | None = None,
    ) -> Path:
        """Download *url* to *dest_path* with optional resume and rate limit."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")

        headers = dict(self._auth_header())
        existing = 0
        if resume and tmp_path.exists():
            existing = tmp_path.stat().st_size
            headers["Range"] = f"bytes={existing}-"

        def handle_resume_response(response: requests.Response) -> bool:
            nonlocal existing, headers
            if response.status_code != 416:
                return False
            if not tmp_path.exists():
                raise RuntimeError(
                    f"Server returned 416 with no partial file for {dest_path.name}"
                )
            size = tmp_path.stat().st_size
            if expected_size is not None and size == expected_size:
                tmp_path.rename(dest_path)
                raise _DownloadAlreadyComplete
            print(
                f"  Resume rejected (416); restarting download "
                f"(part={size}, expected={expected_size})"
            )
            tmp_path.unlink(missing_ok=True)
            existing = 0
            headers = dict(self._auth_header())
            return True

        try:
            resp = _retry_response(
                lambda: self.session.get(url, headers=headers, stream=True, timeout=30),
                max_attempts=MAX_RETRIES,
                connection_message=lambda attempt, total, exc: (
                    f"  Connection error (attempt {attempt}/{total}), retrying in "
                    f"{RETRY_BACKOFF_BASE * (2 ** (attempt - 1))}s: {exc}"
                ),
                server_message=lambda status, attempt, total: (
                    f"  Server error {status} (attempt {attempt}/{total}), retrying in "
                    f"{RETRY_BACKOFF_BASE * (2 ** (attempt - 1))}s"
                ),
                before_status=handle_resume_response,
            )
        except _DownloadAlreadyComplete:
            return dest_path

        mode = "ab" if existing and resp.status_code == 206 else "wb"
        if mode == "wb":
            existing = 0

        total = None
        cl = resp.headers.get("Content-Length")
        if cl:
            total = int(cl) + existing

        if rate_bps:
            chunk_size = min(chunk_size, max(16384, int(rate_bps)))

        t0 = time.monotonic()
        written = 0

        with (
            open(tmp_path, mode) as fh,
            tqdm(
                total=total,
                initial=existing,
                unit="B",
                unit_scale=True,
                desc=dest_path.name,
                leave=True,
            ) as bar,
        ):
            for chunk in resp.iter_content(chunk_size=chunk_size):
                fh.write(chunk)
                written += len(chunk)
                bar.update(len(chunk))

                if rate_bps:
                    expected_elapsed = written / rate_bps
                    actual_elapsed = time.monotonic() - t0
                    if actual_elapsed < expected_elapsed:
                        time.sleep(expected_elapsed - actual_elapsed)

        tmp_path.rename(dest_path)
        return dest_path

    def download_item(
        self,
        item_id: str,
        dest_path: Path,
        chunk_size: int = DEFAULT_CHUNK,
        resume: bool = True,
        rate_bps: float | None = None,
        expected_size: int | None = None,
    ) -> Path:
        """Download the original file for *item_id* via /Items/{id}/Download."""
        return self._download_from_url(
            self._url(f"/Items/{item_id}/Download"),
            dest_path,
            chunk_size=chunk_size,
            resume=resume,
            rate_bps=rate_bps,
            expected_size=expected_size,
        )

    def download_item_stream(
        self,
        item_id: str,
        dest_path: Path,
        chunk_size: int = DEFAULT_CHUNK,
        resume: bool = True,
        rate_bps: float | None = None,
        expected_size: int | None = None,
    ) -> Path:
        """Download like Emby Web playback: PlaybackInfo + /videos/{id}/original.*."""
        url = self.resolve_direct_stream_url(item_id)
        return self._download_from_url(
            url,
            dest_path,
            chunk_size=chunk_size,
            resume=resume,
            rate_bps=rate_bps,
            expected_size=expected_size,
        )

    # -- HLS download --------------------------------------------------------

    def _download_segment(self, url: str, dest: Path) -> None:
        """Download a single HLS segment with retry."""
        resp = _retry_response(
            lambda: self.session.get(
                url, headers=self._auth_header(), stream=True, timeout=30,
            ),
            max_attempts=MAX_RETRIES,
            connection_message=lambda attempt, total, _exc: (
                f"    Segment retry ({attempt}/{total}), waiting "
                f"{RETRY_BACKOFF_BASE * (2 ** (attempt - 1))}s"
            ),
            server_message=lambda status, attempt, total: (
                f"    Segment error {status} ({attempt}/{total}), waiting "
                f"{RETRY_BACKOFF_BASE * (2 ** (attempt - 1))}s"
            ),
        )
        with open(dest, "wb") as f:
            for data in resp.iter_content(chunk_size=DEFAULT_CHUNK):
                f.write(data)

    def download_item_hls(self, item_id: str, dest_path: Path, throttle: float = 0) -> Path:
        """Download via HLS chunks (like a web player) and remux to mkv."""
        dest_path = dest_path.with_suffix(".mkv")
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        item_info = self.get_item_info(item_id)
        sources = item_info.get("MediaSources", [])
        if not sources:
            raise RuntimeError(f"No media sources for item {item_id}")
        media_source_id = sources[0]["Id"]

        play_session_id = hashlib.md5(
            f"hls-{item_id}-{time.time()}".encode()
        ).hexdigest()

        # Omit VideoCodec/AudioCodec=copy (not valid Emby codec ids); let server decide.
        hls_params: dict = {
            "DeviceId": _DEVICE_ID,
            "MediaSourceId": media_source_id,
            "PlaySessionId": play_session_id,
            "SegmentContainer": "ts",
            "BreakOnNonKeyFrames": "false",
        }
        if self.access_token:
            hls_params["api_key"] = self.access_token

        master_path = f"/Videos/{item_id}/master.m3u8"
        master_full_url = self._url(master_path)
        resp = self._get(master_path, params=hls_params)
        master = m3u8.loads(resp.text, uri=master_full_url)

        if not master.playlists:
            raise RuntimeError("No variant streams in master playlist")

        variant_uri = self._ensure_api_key(
            master.playlists[0].absolute_uri, self.access_token
        )

        tmp_dir = dest_path.parent / f".hls-tmp-{item_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            segments: list[Path] = []
            seen_uris: set[str] = set()
            playback_clock = 0.0
            t0 = time.monotonic()
            bar = tqdm(unit=" seg", desc=dest_path.name, leave=True)

            while True:
                resp = self._get(variant_uri)
                media = m3u8.loads(resp.text, uri=variant_uri)

                if media.is_endlist and bar.total is None:
                    bar.total = len(media.segments)
                    bar.refresh()

                for seg in media.segments:
                    seg_uri = seg.absolute_uri
                    if seg_uri in seen_uris:
                        continue
                    seen_uris.add(seg_uri)

                    dl_uri = self._ensure_api_key(seg_uri, self.access_token)
                    seg_path = tmp_dir / f"seg_{len(segments):06d}.ts"
                    self._download_segment(dl_uri, seg_path)
                    segments.append(seg_path)
                    bar.update(1)

                    if throttle and seg.duration:
                        playback_clock += seg.duration / throttle
                        real_elapsed = time.monotonic() - t0
                        if real_elapsed < playback_clock:
                            time.sleep(playback_clock - real_elapsed)

                if media.is_endlist:
                    break

                sleep_time = media.target_duration or 3
                time.sleep(sleep_time)

            bar.close()

            if not segments:
                raise RuntimeError("No segments were downloaded")

            print(f"  Remuxing {len(segments)} segments -> {dest_path.name}")
            remux_segments(tmp_dir, segments, dest_path)

            done_marker = Path(str(dest_path) + ".done")
            done_marker.write_text(str(len(segments)))

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return dest_path
