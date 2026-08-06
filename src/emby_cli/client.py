"""Emby REST API client: auth, browse, download, stream, HLS."""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from urllib.parse import urlencode

import m3u8
import requests
from tqdm import tqdm

from emby_cli.constants import (
    CLIENT_NAME,
    DEFAULT_CHUNK,
    DEVICE_NAME,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
)
from emby_cli.util import remux_segments

_DEVICE_ID = hashlib.md5(CLIENT_NAME.encode()).hexdigest()


class EmbyClient:
    def __init__(self, server_url: str, api_key: str | None = None):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.user_id: str | None = None
        self.access_token: str | None = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "X-Emby-Client": CLIENT_NAME,
            "X-Emby-Device-Name": DEVICE_NAME,
            "X-Emby-Device-Id": _DEVICE_ID,
            "X-Emby-Client-Version": "1.0.0",
        })

    # -- helpers -------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.server_url}/emby{path}" if not path.startswith("http") else path

    def _auth_header(self) -> dict:
        parts = [
            f'MediaBrowser Client="{CLIENT_NAME}"',
            f'Device="{DEVICE_NAME}"',
            f'DeviceId="{_DEVICE_ID}"',
            'Version="1.0.0"',
        ]
        if self.access_token:
            parts.append(f'Token="{self.access_token}"')
        return {"X-Emby-Authorization": ", ".join(parts)}

    def _request_with_retry(self, method: str, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("headers", self._auth_header())
        url = self._url(path)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == MAX_RETRIES:
                    raise
                wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                print(f"  Connection error (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s: {exc}")
                time.sleep(wait)
            except requests.HTTPError as exc:
                if resp.status_code >= 500 and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    print(f"  Server error {resp.status_code} (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError("unreachable")

    def _get(self, path: str, params: dict | None = None, **kwargs) -> requests.Response:
        return self._request_with_retry("GET", path, params=params, **kwargs)

    def _post(self, path: str, payload: dict | None = None) -> requests.Response:
        return self._request_with_retry("POST", path, json=payload)

    # -- auth ----------------------------------------------------------------

    def authenticate(self, username: str, password: str) -> None:
        data = {"Username": username, "Pw": password}
        resp = self._post("/Users/AuthenticateByName", data)
        body = resp.json()
        self.access_token = body["AccessToken"]
        self.user_id = body["User"]["Id"]

    def resolve_user_id(self) -> str:
        if self.user_id:
            return self.user_id
        users = self._get("/Users").json()
        if not users:
            raise RuntimeError("No users found on server")
        self.user_id = users[0]["Id"]
        return self.user_id

    # -- browse --------------------------------------------------------------

    def get_libraries(self) -> list[dict]:
        uid = self.resolve_user_id()
        resp = self._get(f"/Users/{uid}/Views")
        return resp.json().get("Items", [])

    def get_items(
        self,
        parent_id: str | None = None,
        item_type: str | None = None,
        recursive: bool = True,
        start: int = 0,
        limit: int = 200,
    ) -> dict:
        uid = self.resolve_user_id()
        params: dict = {
            "StartIndex": start,
            "Limit": limit,
            "Recursive": str(recursive).lower(),
            "Fields": "Path,MediaSources,DateCreated,Size,RunTimeTicks",
            "SortBy": "SortName",
            "SortOrder": "Ascending",
        }
        if parent_id:
            params["ParentId"] = parent_id
        if item_type:
            params["IncludeItemTypes"] = item_type
        resp = self._get(f"/Users/{uid}/Items", params=params)
        return resp.json()

    def get_all_items(
        self,
        parent_id: str | None = None,
        item_type: str | None = None,
    ) -> list[dict]:
        """Page through all items and return the full list."""
        items: list[dict] = []
        start = 0
        batch = 200
        while True:
            page = self.get_items(parent_id=parent_id, item_type=item_type, start=start, limit=batch)
            items.extend(page.get("Items", []))
            total = page.get("TotalRecordCount", 0)
            start += batch
            if start >= total:
                break
        return items

    def get_item_info(self, item_id: str) -> dict:
        uid = self.resolve_user_id()
        resp = self._get(f"/Users/{uid}/Items/{item_id}")
        return resp.json()

    def search_items(self, query: str, item_types: str = "Movie", limit: int = 25) -> list[dict]:
        uid = self.resolve_user_id()
        params = {
            "SearchTerm": query,
            "Limit": limit,
            "Recursive": "true",
            "Fields": "Path,MediaSources,MediaStreams,Size,RunTimeTicks,ProductionYear",
            "IncludeItemTypes": item_types,
        }
        resp = self._get(f"/Users/{uid}/Items", params=params)
        return resp.json().get("Items", [])

    def get_show_episodes(self, series_id: str, season: int | None = None) -> list[dict]:
        uid = self.resolve_user_id()
        params: dict = {
            "UserId": uid,
            "Fields": "Path,MediaSources,MediaStreams,Size,RunTimeTicks,ProductionYear",
        }
        if season is not None:
            params["Season"] = season
        resp = self._get(f"/Shows/{series_id}/Episodes", params=params)
        return resp.json().get("Items", [])

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
        # Empty DeviceProfile: let the server decide; Emby Web sends one, but
        # DirectStreamUrl is still returned without it for compatible files.
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
            device_id = _DEVICE_ID
            qs = {
                "DeviceId": device_id,
                "MediaSourceId": source.get("Id") or media_source_id or item_id,
                "PlaySessionId": play_session_id
                or hashlib.md5(f"stream-{item_id}-{time.time()}".encode()).hexdigest(),
            }
            if self.access_token:
                qs["api_key"] = self.access_token
            direct = f"/Videos/{item_id}/original.{container}?{urlencode(qs)}"

        if direct.startswith("http"):
            return direct
        if not direct.startswith("/"):
            direct = "/" + direct
        # PlaybackInfo returns "/videos/..." (no /emby prefix)
        if direct.lower().startswith("/emby/"):
            return f"{self.server_url}{direct}"
        return f"{self.server_url}/emby{direct}"

    # -- download ------------------------------------------------------------

    def _download_from_url(
        self,
        url: str,
        dest_path: Path,
        chunk_size: int = DEFAULT_CHUNK,
        resume: bool = True,
        rate_bps: float | None = None,
    ) -> Path:
        """Download *url* to *dest_path* with optional resume and rate limit."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")

        headers = dict(self._auth_header())
        existing = 0
        if resume and tmp_path.exists():
            existing = tmp_path.stat().st_size
            headers["Range"] = f"bytes={existing}-"

        resp = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, headers=headers, stream=True, timeout=30)
                if resp.status_code == 416:
                    if tmp_path.exists():
                        tmp_path.rename(dest_path)
                    return dest_path
                resp.raise_for_status()
                break
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == MAX_RETRIES:
                    raise
                wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                print(f"  Connection error (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s: {exc}")
                time.sleep(wait)
            except requests.HTTPError:
                if resp is not None and resp.status_code >= 500 and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    print(f"  Server error {resp.status_code} (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise

        total = None
        cl = resp.headers.get("Content-Length")
        if cl:
            total = int(cl) + existing

        mode = "ab" if existing and resp.status_code == 206 else "wb"
        if mode == "wb":
            existing = 0

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
    ) -> Path:
        """Download the original file for *item_id* via /Items/{id}/Download."""
        return self._download_from_url(
            self._url(f"/Items/{item_id}/Download"),
            dest_path,
            chunk_size=chunk_size,
            resume=resume,
            rate_bps=rate_bps,
        )

    def download_item_stream(
        self,
        item_id: str,
        dest_path: Path,
        chunk_size: int = DEFAULT_CHUNK,
        resume: bool = True,
        rate_bps: float | None = None,
    ) -> Path:
        """Download like Emby Web playback: PlaybackInfo + /videos/{id}/original.*."""
        url = self.resolve_direct_stream_url(item_id)
        return self._download_from_url(
            url,
            dest_path,
            chunk_size=chunk_size,
            resume=resume,
            rate_bps=rate_bps,
        )

    # -- HLS download --------------------------------------------------------

    def _download_segment(self, url: str, dest: Path) -> None:
        """Download a single HLS segment with retry."""
        resp = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(
                    url, headers=self._auth_header(), stream=True, timeout=30,
                )
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for data in resp.iter_content(chunk_size=DEFAULT_CHUNK):
                        f.write(data)
                return
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == MAX_RETRIES:
                    raise
                wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                print(f"    Segment retry ({attempt}/{MAX_RETRIES}), waiting {wait}s")
                time.sleep(wait)
            except requests.HTTPError:
                if resp is not None and resp.status_code >= 500 and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    print(f"    Segment error {resp.status_code} ({attempt}/{MAX_RETRIES}), waiting {wait}s")
                    time.sleep(wait)
                else:
                    raise

    def download_item_hls(self, item_id: str, dest_path: Path, throttle: float = 0) -> Path:
        """Download via HLS chunks (like a web player) and remux to mkv."""
        dest_path = dest_path.with_suffix(".mkv")
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        item_info = self.get_item_info(item_id)
        sources = item_info.get("MediaSources", [])
        if not sources:
            raise RuntimeError(f"No media sources for item {item_id}")
        media_source_id = sources[0]["Id"]

        device_id = _DEVICE_ID
        play_session_id = hashlib.md5(
            f"hls-{item_id}-{time.time()}".encode()
        ).hexdigest()

        hls_params: dict = {
            "DeviceId": device_id,
            "MediaSourceId": media_source_id,
            "PlaySessionId": play_session_id,
            "VideoCodec": "copy",
            "AudioCodec": "copy",
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

        variant_uri = master.playlists[0].absolute_uri
        if self.access_token and "api_key" not in variant_uri:
            sep = "&" if "?" in variant_uri else "?"
            variant_uri += f"{sep}api_key={self.access_token}"

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

                    dl_uri = seg_uri
                    if self.access_token and "api_key" not in dl_uri:
                        sep = "&" if "?" in dl_uri else "?"
                        dl_uri += f"{sep}api_key={self.access_token}"

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
