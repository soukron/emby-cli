"""Tests for Stats / exit codes and output streams."""

from __future__ import annotations

from pathlib import Path

from emby_cli.output import (
    Stats,
    print_done,
    print_download,
    print_error,
    print_skip,
)


def test_exit_code_ok():
    assert Stats().exit_code() == 0


def test_exit_code_error():
    assert Stats(error=1).exit_code() == 1


def test_exit_code_not_found_optional():
    s = Stats(not_found=2)
    assert s.exit_code() == 0
    assert s.exit_code(fail_on_not_found=True) == 1


def test_print_error_goes_to_stderr(capsys):
    print_error("boom", idx=2, total=5)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "[2/5] error: boom\n"


def test_print_download_and_skip_go_to_stdout(capsys):
    dest = Path("out.mkv")
    print_download("Movie", dest, method="stream", idx=1, total=2)
    print_skip("Movie", dest, idx=1, total=2)
    print_done(Stats(ok=1, skip=1))
    captured = capsys.readouterr()
    assert "[1/2] download (stream): Movie -> out.mkv" in captured.out
    assert "[1/2] skip: Movie -> out.mkv" in captured.out
    assert "Done. ok=1 skip=1 error=0" in captured.out
    assert captured.err == ""
