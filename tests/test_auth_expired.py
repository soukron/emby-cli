"""UX when a cached AccessToken is rejected (401)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from emby_cli.auth_cache import AuthCacheEntry, load_auth_cache, save_auth_cache
from emby_cli.cli import main
from emby_cli.client import AuthenticationError, EmbyClient


def _resp(status_code):
    r = MagicMock()
    r.status_code = status_code
    if status_code >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(response=r)
    else:
        r.raise_for_status.return_value = None
    return r


def test_stale_cache_401_raises_auth_error_and_clears_store(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "stale-tok", "uid-1")
    )
    client = EmbyClient("http://host:8096")
    client.ensure_user_session("alice", None)  # restore cache; no password for reauth
    assert client.access_token == "stale-tok"

    with patch.object(client.session, "request", return_value=_resp(401)):
        with pytest.raises(AuthenticationError, match="emby-cli login"):
            client._get("/Users/uid-1/Views")

    assert load_auth_cache(server_url="http://host:8096", username="alice") is None
    assert client.access_token is None


def test_main_prints_friendly_message_on_expired_session(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("EMBY_CACHE_DIR", str(tmp_path))
    save_auth_cache(
        AuthCacheEntry.create("http://host:8096", "alice", "stale-tok", "uid-1")
    )
    monkeypatch.setattr(
        "sys.argv",
        ["emby-cli", "--server", "http://host:8096", "library", "list"],
    )

    client = EmbyClient("http://host:8096", use_auth_cache=True)
    client.access_token = "stale-tok"
    client.user_id = "uid-1"
    client._username = "alice"

    with (
        patch("emby_cli.cli._open_client", return_value=client),
        patch.object(client.libraries, "search", side_effect=AuthenticationError(
            "Session expired or credentials were rejected by the server. "
            "Run `emby-cli login` (or pass a valid --api-key) and try again."
        )),
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "error: Session expired" in err
    assert "emby-cli login" in err
    assert "Traceback" not in err
