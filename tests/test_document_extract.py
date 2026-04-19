"""Tests for the shared document extraction helpers."""

from pathlib import Path

from klaude.tools._document import (
    MAX_EXTRACTED_BYTES,
    extract,
    _apply_cap,
    _wrap,
)


def test_wrap_includes_system_reminder_and_document_tags() -> None:
    out = _wrap("hello", path="/x.txt", format="txt")
    assert "<system-reminder>" in out
    assert "</system-reminder>" in out
    assert 'path="/x.txt"' in out
    assert 'format="txt"' in out
    assert "hello" in out
    assert "untrusted data" in out


def test_cap_truncates_long_content() -> None:
    huge = "a" * (MAX_EXTRACTED_BYTES + 5000)
    capped = _apply_cap(huge)
    assert "[truncated at 200 KB — original document was larger]" in capped
    head = capped.split("\n\n[truncated")[0]
    assert len(head.encode("utf-8")) <= MAX_EXTRACTED_BYTES


def test_cap_leaves_short_content_alone() -> None:
    assert _apply_cap("short") == "short"


def test_extract_missing_file(tmp_path: Path) -> None:
    out = extract(tmp_path / "nope.pdf")
    assert out.startswith("Error:")
    assert "not found" in out.lower() or "no such" in out.lower()


def test_extract_unsupported_extension(tmp_path: Path) -> None:
    p = tmp_path / "foo.bogus"
    p.write_text("whatever")
    out = extract(p)
    assert out.startswith("Error:")
    assert "unsupported" in out.lower() or "not supported" in out.lower()
