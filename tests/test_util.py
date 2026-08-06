"""Tests for path/size helpers."""

from __future__ import annotations

from pathlib import Path

from emby_cli.util import build_dest_path, format_size, should_skip, should_skip_hls


def test_format_size():
    assert format_size(None) == "?"
    assert format_size(512) == "512.0 B"
    assert "KiB" in format_size(2048)


def test_build_dest_path_from_server_path():
    item = {"Id": "1", "Name": "Film", "Path": "/mnt/media/Movies/Film/Film.mkv"}
    dest = build_dest_path(item, Path("/out"))
    assert dest == Path("/out/Movies/Film/Film.mkv")


def test_build_dest_path_fallback():
    item = {"Id": "abc", "Name": "Film", "MediaSources": [{"Container": "mp4"}]}
    dest = build_dest_path(item, Path("/out"))
    assert dest == Path("/out/Film.mp4")


def test_should_skip_size_match(tmp_path):
    dest = tmp_path / "f.mkv"
    dest.write_bytes(b"x" * 100)
    item = {"MediaSources": [{"Size": 100}]}
    assert should_skip(item, dest) is True
    item2 = {"MediaSources": [{"Size": 50}]}
    assert should_skip(item2, dest) is False


def test_should_skip_hls(tmp_path):
    dest = tmp_path / "f.mp4"
    mkv = dest.with_suffix(".mkv")
    assert should_skip_hls(dest) is False
    mkv.write_text("x")
    assert should_skip_hls(dest) is False
    Path(str(mkv) + ".done").write_text("1")
    assert should_skip_hls(dest) is True
