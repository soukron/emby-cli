"""Exhaustive retry / backoff matrix for _retry_response and callers."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
import requests

from emby_cli.client import _AUTH_PATH, EmbyClient
from emby_cli.constants import MAX_RETRIES, RETRY_BACKOFF_BASE

# ── helpers ──────────────────────────────────────────────────────────────


def _resp(status_code, *, headers=None, json_data=None, chunks=None):
    """Build a mock requests.Response with optional body helpers."""
    r = MagicMock()
    r.status_code = status_code
    r.headers = headers if headers is not None else {}
    if status_code >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(response=r)
    else:
        r.raise_for_status.return_value = None
    if json_data is not None:
        r.json.return_value = json_data
    if chunks is not None:
        r.iter_content.return_value = chunks
    return r


def _client(**kw):
    return EmbyClient("http://host:8096", api_key="k", **kw)


def _backoff(attempt):
    """Expected sleep seconds for a 1-based attempt number."""
    return RETRY_BACKOFF_BASE * (2 ** (attempt - 1))


# ── 1. ConnectionError ──────────────────────────────────────────────────


class TestConnectionErrorRetry:

    def test_retries_with_backoff_until_success(self):
        c = _client()
        errs = [requests.ConnectionError("refused")] * 2
        ok = _resp(200)

        with (
            patch.object(c.session, "request", side_effect=[*errs, ok]),
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            assert c._get("/Items") is ok

        assert sleep.call_count == 2
        sleep.assert_has_calls([call(_backoff(1)), call(_backoff(2))])

    def test_exhausts_retries_and_raises(self):
        c = _client()
        errs = [requests.ConnectionError("refused")] * MAX_RETRIES

        with (
            patch.object(c.session, "request", side_effect=errs),
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            with pytest.raises(requests.ConnectionError):
                c._get("/Items")

        assert sleep.call_count == MAX_RETRIES - 1


# ── 2. Timeout ──────────────────────────────────────────────────────────


class TestTimeoutRetry:

    def test_retries_with_backoff_until_success(self):
        c = _client()
        errs = [requests.Timeout("timed out")] * 2
        ok = _resp(200)

        with (
            patch.object(c.session, "request", side_effect=[*errs, ok]),
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            assert c._get("/Items") is ok

        assert sleep.call_count == 2
        sleep.assert_has_calls([call(_backoff(1)), call(_backoff(2))])

    def test_exhausts_retries_and_raises(self):
        c = _client()
        errs = [requests.Timeout("timed out")] * MAX_RETRIES

        with (
            patch.object(c.session, "request", side_effect=errs),
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            with pytest.raises(requests.Timeout):
                c._get("/Items")

        assert sleep.call_count == MAX_RETRIES - 1


# ── 3. HTTP 5xx ─────────────────────────────────────────────────────────


class TestHttp5xxRetry:

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_retries_server_error(self, status):
        c = _client()
        bad = _resp(status)
        ok = _resp(200)

        with (
            patch.object(c.session, "request", side_effect=[bad, ok]),
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            assert c._get("/Items", retries=2) is ok

        sleep.assert_called_once_with(_backoff(1))

    def test_backoff_values_30_60_120_240(self):
        """Four consecutive 500s produce backoff 30, 60, 120, 240."""
        c = _client()
        bads = [_resp(500) for _ in range(4)]
        ok = _resp(200)

        with (
            patch.object(c.session, "request", side_effect=[*bads, ok]),
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            assert c._get("/Items") is ok

        assert sleep.call_count == 4
        sleep.assert_has_calls([call(30), call(60), call(120), call(240)])

    def test_exhausts_retries_and_raises(self):
        c = _client()
        bads = [_resp(503) for _ in range(MAX_RETRIES)]

        with (
            patch.object(c.session, "request", side_effect=bads),
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            with pytest.raises(requests.HTTPError) as exc_info:
                c._get("/Items")

        assert exc_info.value.response.status_code == 503
        assert sleep.call_count == MAX_RETRIES - 1

    def test_request_retries_server_error_with_backoff(self):
        """Moved from test_client — 503 then 200, retries=2."""
        c = _client()
        unavailable = MagicMock(status_code=503)
        unavailable.raise_for_status.side_effect = requests.HTTPError(
            response=unavailable
        )
        ok = MagicMock(status_code=200)
        ok.raise_for_status.return_value = None

        with (
            patch.object(
                c.session, "request", side_effect=[unavailable, ok]
            ) as req,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            assert c._get("/System/Info", retries=2) is ok

        assert req.call_count == 2
        sleep.assert_called_once_with(30)


# ── 4. HTTP 4xx (no retry) ──────────────────────────────────────────────


class TestHttp4xxNoRetry:

    @pytest.mark.parametrize("status", [400, 403, 404])
    def test_fails_immediately(self, status):
        c = _client()
        bad = _resp(status)

        with (
            patch.object(c.session, "request", side_effect=[bad]) as req,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            with pytest.raises(requests.HTTPError) as exc_info:
                c._get("/Items")

        assert exc_info.value.response.status_code == status
        assert req.call_count == 1
        sleep.assert_not_called()


# ── 5. HTTP 401 reauth ──────────────────────────────────────────────────


class TestHttp401Reauth:

    @staticmethod
    def _authed_client():
        c = EmbyClient("http://host:8096", use_auth_cache=False)
        c._username = "user"
        c._password = "pass"
        c.access_token = "old-token"
        c.user_id = "uid"
        return c

    def test_reauths_once_then_retries(self):
        """401 → reauth → retry with new token → 200."""
        c = self._authed_client()

        with (
            patch.object(
                c.session, "request",
                side_effect=[
                    _resp(401),
                    _resp(200, json_data={"AccessToken": "new", "User": {"Id": "uid"}}),
                    _resp(200, json_data={"ok": True}),
                ],
            ) as req,
            patch("emby_cli.client.time.sleep") as sleep,
            patch("emby_cli.client.clear_auth_cache"),
        ):
            result = c._get("/System/Info")

        assert result.json() == {"ok": True}
        assert c.access_token == "new"
        assert req.call_count == 3
        sleep.assert_not_called()

    def test_retry_uses_new_token_in_header(self):
        """After reauth the Authorization header carries the fresh token."""
        c = self._authed_client()

        with (
            patch.object(
                c.session, "request",
                side_effect=[
                    _resp(401),
                    _resp(200, json_data={"AccessToken": "fresh", "User": {"Id": "uid"}}),
                    _resp(200),
                ],
            ) as req,
            patch("emby_cli.client.time.sleep"),
            patch("emby_cli.client.clear_auth_cache"),
        ):
            c._get("/System/Info")

        auth_hdr = req.call_args_list[2].kwargs["headers"]["X-Emby-Authorization"]
        assert 'Token="fresh"' in auth_hdr

    def test_second_401_propagates_without_retry_loop(self):
        """After one successful reauth, a second 401 is not retried.

        Sequence: GET→401, POST(reauth)→200, GET→401 → raises.
        """
        c = self._authed_client()

        with (
            patch.object(
                c.session, "request",
                side_effect=[
                    _resp(401),
                    _resp(200, json_data={"AccessToken": "new", "User": {"Id": "uid"}}),
                    _resp(401),
                ],
            ) as req,
            patch("emby_cli.client.time.sleep"),
            patch("emby_cli.client.clear_auth_cache"),
        ):
            with pytest.raises(requests.HTTPError) as exc_info:
                c._get("/System/Info")

        assert exc_info.value.response.status_code == 401
        assert req.call_count == 3

    def test_no_reauth_without_password(self):
        c = EmbyClient("http://host:8096", use_auth_cache=False)
        c._username = "user"
        c._password = None
        c.access_token = "tok"

        with (
            patch.object(c.session, "request", side_effect=[_resp(401)]) as req,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            with pytest.raises(requests.HTTPError):
                c._get("/Items")

        assert req.call_count == 1
        sleep.assert_not_called()

    def test_no_reauth_without_username(self):
        c = EmbyClient("http://host:8096", use_auth_cache=False)
        c._username = None
        c._password = "pass"
        c.access_token = "tok"

        with (
            patch.object(c.session, "request", side_effect=[_resp(401)]) as req,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            with pytest.raises(requests.HTTPError):
                c._get("/Items")

        assert req.call_count == 1
        sleep.assert_not_called()

    def test_no_reauth_on_authenticate_path(self):
        """401 on /Users/AuthenticateByName never triggers reauth."""
        c = self._authed_client()

        with (
            patch.object(c.session, "request", side_effect=[_resp(401)]) as req,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            with pytest.raises(requests.HTTPError):
                c._post(_AUTH_PATH, {"Username": "u", "Pw": "p"})

        assert req.call_count == 1
        sleep.assert_not_called()


# ── 6. retries=1 ────────────────────────────────────────────────────────


class TestRetriesOne:

    def test_connection_error_no_retry(self):
        c = _client()
        with (
            patch.object(
                c.session, "request",
                side_effect=requests.ConnectionError("refused"),
            ) as req,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            with pytest.raises(requests.ConnectionError):
                c._get("/Items", retries=1)

        assert req.call_count == 1
        sleep.assert_not_called()

    def test_5xx_no_retry(self):
        c = _client()
        with (
            patch.object(c.session, "request", side_effect=[_resp(500)]) as req,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            with pytest.raises(requests.HTTPError):
                c._get("/Items", retries=1)

        assert req.call_count == 1
        sleep.assert_not_called()

    def test_preserves_401_reauth(self):
        """retries=1 still allows exactly one reauth cycle."""
        c = EmbyClient("http://host:8096", use_auth_cache=False)
        c._username = "user"
        c._password = "pass"
        c.access_token = "old"
        c.user_id = "uid"

        with (
            patch.object(
                c.session, "request",
                side_effect=[
                    _resp(401),
                    _resp(200, json_data={"AccessToken": "new", "User": {"Id": "uid"}}),
                    _resp(200),
                ],
            ) as req,
            patch("emby_cli.client.time.sleep") as sleep,
            patch("emby_cli.client.clear_auth_cache"),
        ):
            result = c._get("/Items", retries=1)

        assert result.status_code == 200
        assert req.call_count == 3
        sleep.assert_not_called()


# ── 7. HLS segment retry ───────────────────────────────────────────────


class TestHlsSegmentRetry:

    def test_retries_when_stream_body_disconnects(self, tmp_path):
        """Moved from test_client — partial body then ConnectionError."""
        c = _client()

        def interrupted_body():
            yield b"partial-"
            raise requests.ConnectionError("disconnected")

        interrupted = MagicMock()
        interrupted.raise_for_status.return_value = None
        interrupted.iter_content.return_value = interrupted_body()
        complete = MagicMock()
        complete.raise_for_status.return_value = None
        complete.iter_content.return_value = [b"complete-segment"]
        dest = tmp_path / "segment.ts"

        with (
            patch.object(
                c.session, "get", side_effect=[interrupted, complete]
            ) as get,
            patch("emby_cli.client.time.sleep"),
        ):
            c._download_segment("http://host/segment.ts", dest)

        assert get.call_count == 2
        assert dest.read_bytes() == b"complete-segment"

    def test_connection_error_before_response(self, tmp_path):
        c = _client()
        ok = MagicMock()
        ok.raise_for_status.return_value = None
        ok.iter_content.return_value = [b"full-segment"]
        dest = tmp_path / "segment.ts"

        with (
            patch.object(
                c.session, "get",
                side_effect=[requests.ConnectionError("refused"), ok],
            ) as get,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            c._download_segment("http://host/segment.ts", dest)

        assert get.call_count == 2
        assert dest.read_bytes() == b"full-segment"
        sleep.assert_called_once_with(_backoff(1))

    def test_overwrites_partial_on_retry(self, tmp_path):
        """Second successful attempt completely replaces partial data."""
        c = _client()
        dest = tmp_path / "segment.ts"

        def interrupted_body():
            yield b"PARTIAL"
            raise requests.ConnectionError("mid-stream")

        interrupted = MagicMock()
        interrupted.raise_for_status.return_value = None
        interrupted.iter_content.return_value = interrupted_body()
        complete = MagicMock()
        complete.raise_for_status.return_value = None
        complete.iter_content.return_value = [b"FRESH"]

        with (
            patch.object(c.session, "get", side_effect=[interrupted, complete]),
            patch("emby_cli.client.time.sleep"),
        ):
            c._download_segment("http://host/segment.ts", dest)

        assert dest.read_bytes() == b"FRESH"

    def test_exhausts_retries_raises(self, tmp_path):
        c = _client()
        dest = tmp_path / "segment.ts"
        errs = [requests.ConnectionError("down")] * MAX_RETRIES

        with (
            patch.object(c.session, "get", side_effect=errs),
            patch("emby_cli.client.time.sleep"),
        ):
            with pytest.raises(requests.ConnectionError):
                c._download_segment("http://host/segment.ts", dest)

    def test_5xx_retries_segment(self, tmp_path):
        c = _client()
        dest = tmp_path / "segment.ts"
        ok = MagicMock()
        ok.raise_for_status.return_value = None
        ok.iter_content.return_value = [b"segment-data"]

        with (
            patch.object(
                c.session, "get", side_effect=[_resp(502), ok]
            ) as get,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            c._download_segment("http://host/segment.ts", dest)

        assert get.call_count == 2
        assert dest.read_bytes() == b"segment-data"
        sleep.assert_called_once_with(_backoff(1))


# ── 8. Download 416 ─────────────────────────────────────────────────────


class TestDownload416:

    def test_promotes_complete_partial_file(self, tmp_path):
        """Moved from test_client — 416 + matching size → rename .part."""
        c = _client()
        dest = tmp_path / "movie.mkv"
        partial = tmp_path / "movie.mkv.part"
        partial.write_bytes(b"complete")
        response = MagicMock(status_code=416)

        with patch.object(c.session, "get", return_value=response) as get:
            result = c._download_from_url(
                "http://host/movie.mkv",
                dest,
                expected_size=len(b"complete"),
            )

        assert result == dest
        assert dest.read_bytes() == b"complete"
        assert not partial.exists()
        assert get.call_count == 1

    def test_restarts_without_range_header(self, tmp_path):
        """Moved from test_client — 416 + size mismatch → drop Range, re-download."""
        c = _client()
        dest = tmp_path / "movie.mkv"
        partial = tmp_path / "movie.mkv.part"
        partial.write_bytes(b"stale")
        rejected = MagicMock(status_code=416)
        fresh = MagicMock(status_code=200)
        fresh.raise_for_status.return_value = None
        fresh.headers = {}
        fresh.iter_content.return_value = [b"fresh"]

        with patch.object(
            c.session, "get", side_effect=[rejected, fresh]
        ) as get:
            result = c._download_from_url(
                "http://host/movie.mkv",
                dest,
                expected_size=10,
            )

        assert result == dest
        assert dest.read_bytes() == b"fresh"
        assert "Range" in get.call_args_list[0].kwargs["headers"]
        assert "Range" not in get.call_args_list[1].kwargs["headers"]

    def test_no_partial_file_raises(self, tmp_path):
        """416 with no .part file on disk → RuntimeError."""
        c = _client()
        dest = tmp_path / "movie.mkv"
        response = MagicMock(status_code=416)

        with patch.object(c.session, "get", return_value=response):
            with pytest.raises(RuntimeError, match="416 with no partial file"):
                c._download_from_url("http://host/movie.mkv", dest)


# ── 9. Download transient errors ────────────────────────────────────────


class TestDownloadTransientErrors:

    def test_5xx_retries_with_backoff(self, tmp_path):
        c = _client()
        dest = tmp_path / "movie.mkv"
        ok = _resp(200, chunks=[b"content"])

        with (
            patch.object(c.session, "get", side_effect=[_resp(503), ok]) as get,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            result = c._download_from_url(
                "http://host/movie.mkv", dest, resume=False
            )

        assert result == dest
        assert dest.read_bytes() == b"content"
        assert get.call_count == 2
        sleep.assert_called_once_with(_backoff(1))

    def test_4xx_non_416_no_retry(self, tmp_path):
        c = _client()
        dest = tmp_path / "movie.mkv"

        with (
            patch.object(c.session, "get", side_effect=[_resp(403)]) as get,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            with pytest.raises(requests.HTTPError) as exc_info:
                c._download_from_url(
                    "http://host/movie.mkv", dest, resume=False
                )

        assert exc_info.value.response.status_code == 403
        assert get.call_count == 1
        sleep.assert_not_called()

    def test_connection_error_retries(self, tmp_path):
        c = _client()
        dest = tmp_path / "movie.mkv"
        ok = _resp(200, chunks=[b"data"])

        with (
            patch.object(
                c.session, "get",
                side_effect=[requests.ConnectionError("down"), ok],
            ) as get,
            patch("emby_cli.client.time.sleep") as sleep,
        ):
            result = c._download_from_url(
                "http://host/movie.mkv", dest, resume=False
            )

        assert result == dest
        assert dest.read_bytes() == b"data"
        assert get.call_count == 2
        sleep.assert_called_once_with(_backoff(1))
