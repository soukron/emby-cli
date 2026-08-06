"""Tests for Stats / exit codes."""

from __future__ import annotations

from emby_cli.output import Stats


def test_exit_code_ok():
    assert Stats().exit_code() == 0


def test_exit_code_error():
    assert Stats(error=1).exit_code() == 1


def test_exit_code_not_found_optional():
    s = Stats(not_found=2)
    assert s.exit_code() == 0
    assert s.exit_code(fail_on_not_found=True) == 1
