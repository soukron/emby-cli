"""Tests for path/size helpers."""

from __future__ import annotations

from pathlib import Path

from emby_cli.util import (
    build_dest_path,
    format_size,
    mirrored_path_parts,
    safe_output_dir_name,
    should_skip,
    should_skip_hls,
)


def test_format_size():
    assert format_size(None) == "?"
    assert format_size(512) == "512.0 B"
    assert "KiB" in format_size(2048)


def test_build_dest_path_from_server_path():
    item = {"Id": "1", "Name": "Film", "Path": "/mnt/media/Movies/Film/Film.mkv"}
    dest = build_dest_path(item, Path("/out"))
    assert dest == Path("/out/Film.mkv")


def test_build_dest_path_mirror_path():
    item = {"Id": "1", "Name": "Film", "Path": "/mnt/media/Movies/Film/Film.mkv"}
    dest = build_dest_path(item, Path("/out"), mirror_path=True)
    assert dest == Path("/out/Movies/Film/Film.mkv")


def test_mirrored_path_parts_strips_configured_prefix():
    parts = mirrored_path_parts(
        "/mnt/media/tv/Show/Season 01/ep.mkv",
        path_strip="/mnt/media",
    )
    assert parts == ("tv", "Show", "Season 01", "ep.mkv")


def test_mirrored_path_parts_falls_back_when_prefix_does_not_match():
    parts = mirrored_path_parts(
        "/srv/storage/Movies/Film/Film.mkv",
        path_strip="/mnt/media",
    )
    assert parts == ("Movies", "Film", "Film.mkv")


def test_build_dest_path_mirror_path_with_path_strip():
    item = {"Id": "1", "Name": "Film", "Path": "/mnt/media/Movies/Film/Film.mkv"}
    dest = build_dest_path(
        item,
        Path("/out"),
        mirror_path=True,
        path_strip="/mnt/media",
    )
    assert dest == Path("/out/Movies/Film/Film.mkv")


def test_safe_output_dir_name():
    assert safe_output_dir_name("  Películas  ") == "Películas"
    assert safe_output_dir_name("Star/Wars") == "Star-Wars"
    assert safe_output_dir_name("   ") == "?"


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
