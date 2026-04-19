"""read_file should dispatch binary extensions through _document.extract."""

from pathlib import Path

from klaude.tools.read_file import handle_read_file
from tests.fixtures import make_docx


def test_read_file_text_unchanged(tmp_path: Path) -> None:
    p = tmp_path / "s.py"
    p.write_text("print('hi')\n")
    out = handle_read_file(str(p))
    assert out == "print('hi')\n"
    assert "<system-reminder>" not in out


def test_read_file_dispatches_docx(tmp_path: Path) -> None:
    p = make_docx(tmp_path / "a.docx", ["via read_file"])
    out = handle_read_file(str(p))
    assert "via read_file" in out
    assert "<system-reminder>" in out
    assert 'format="docx"' in out


def test_read_file_unknown_binary_clean_error(tmp_path: Path) -> None:
    p = tmp_path / "x.bin"
    p.write_bytes(b"\x00\x01\x02\xff\xfe")
    out = handle_read_file(str(p))
    assert out.startswith("Error:")
    assert "binary" in out.lower()
    assert "read_document" in out
