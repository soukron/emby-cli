"""Tests for download_one_item / should_skip_item / do_download."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import requests

from emby_cli.item_ops import (
    do_download,
    download_items,
    download_one_item,
    should_skip_item,
)


def _item(iid: str = "1", size: int = 100, name: str = "Movie") -> dict:
    return {
        "Id": iid,
        "Name": name,
        "Type": "Movie",
        "Path": f"/media/Movies/{name}/{name}.mkv",
        "MediaSources": [{"Size": size, "Container": "mkv"}],
    }


def test_should_skip_when_size_matches(tmp_path):
    item = _item(size=10)
    dest = tmp_path / "Movie.mkv"
    dest.write_bytes(b"x" * 10)
    assert should_skip_item(item, dest, "download", force=False) is True


def test_should_skip_force_never_skips(tmp_path):
    item = _item(size=10)
    dest = tmp_path / "f.mkv"
    dest.write_bytes(b"x" * 10)
    assert should_skip_item(item, dest, "download", force=True) is False


def test_should_skip_hls_requires_done_marker(tmp_path):
    dest = tmp_path / "ep.mkv"
    dest.write_bytes(b"data")
    assert should_skip_item(_item(), dest, "hls", force=False) is False
    Path(str(dest) + ".done").write_text("ok")
    assert should_skip_item(_item(), dest, "hls", force=False) is True


def test_do_download_dispatches_methods():
    client = MagicMock()
    item = _item()
    dest = Path("out.mkv")

    do_download(client, "1", item, dest, "download", 0)
    client.download_item.assert_called_once()
    client.reset_mock()

    do_download(client, "1", item, dest, "stream", 0)
    client.download_item_stream.assert_called_once()
    client.reset_mock()

    do_download(client, "1", item, dest, "hls", 0)
    client.download_item_hls.assert_called_once_with("1", dest, throttle=0)


def test_download_one_dry_run_does_not_call_client(tmp_path, capsys):
    client = MagicMock()
    result = download_one_item(
        client,
        _item(),
        tmp_path,
        method="download",
        force=False,
        throttle=0,
        dry_run=True,
    )
    assert result == "dry_run"
    client.download_item.assert_not_called()
    assert "dry-run:" in capsys.readouterr().out


def test_download_one_skip(tmp_path, capsys):
    client = MagicMock()
    item = _item(size=5)
    (tmp_path / "Movie.mkv").write_bytes(b"12345")
    result = download_one_item(
        client, item, tmp_path, method="download", force=False, throttle=0
    )
    assert result == "skip"
    client.download_item.assert_not_called()
    assert "skip:" in capsys.readouterr().out


def test_download_one_error_goes_to_stderr(tmp_path, capsys):
    client = MagicMock()
    client.download_item.side_effect = requests.ConnectionError("down")
    result = download_one_item(
        client, _item(), tmp_path, method="download", force=False, throttle=0
    )
    assert result == "error"
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "error:" not in captured.out


def test_download_one_ok(tmp_path, capsys):
    client = MagicMock()
    result = download_one_item(
        client, _item(), tmp_path, method="stream", force=False, throttle=0
    )
    assert result == "ok"
    client.download_item_stream.assert_called_once()
    assert "download (stream):" in capsys.readouterr().out


def test_download_items_counts_dry_run_as_ok(tmp_path):
    client = MagicMock()
    stats = download_items(
        client,
        [_item("1"), _item("2")],
        tmp_path,
        method="download",
        force=False,
        throttle=0,
        dry_run=True,
    )
    assert (stats.ok, stats.skip, stats.error) == (2, 0, 0)
    client.download_item.assert_not_called()
