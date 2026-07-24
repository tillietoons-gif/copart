"""Tests for utility helpers."""

from __future__ import annotations

from pathlib import Path

from copart_automation.app.utils import (
    ensure_directory,
    extract_domain_from_url,
    format_time_delta,
    safe_path_join,
)


def test_safe_path_join_within_base(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    target = safe_path_join(base, "subdir", "file.txt")
    assert target.parent == base / "subdir"
    assert target.exists() is False


def test_safe_path_join_detects_traversal(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    try:
        safe_path_join(base, "..", "etc", "passwd")
        assert False, "Expected ValueError for path traversal"
    except ValueError as exc:
        assert "outside" in str(exc)


def test_ensure_directory_creates_parent(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "file.txt"
    assert not path.parent.exists()
    result = ensure_directory(path)
    assert result == path
    assert path.parent.exists()


def test_format_time_delta_seconds() -> None:
    assert format_time_delta(12.3) == "12.3s"


def test_format_time_delta_minutes() -> None:
    assert format_time_delta(125) == "2m 5s"


def test_extract_domain_from_url() -> None:
    assert extract_domain_from_url("https://www.copart.com/search?q=test") == "www.copart.com"
