"""Tests for the public read_document tool wrapper."""

from pathlib import Path

from klaude.tools.read_document import tool
from tests.fixtures import make_docx


def test_read_document_tool_returns_wrapped_content(tmp_path: Path) -> None:
    p = make_docx(tmp_path / "a.docx", ["hello doc"])
    result = tool.handler(path=str(p))
    assert "hello doc" in result
    assert "<system-reminder>" in result
    assert 'format="docx"' in result


def test_read_document_tool_schema_minimal() -> None:
    assert tool.name == "read_document"
    assert tool.parameters["required"] == ["path"]
    assert "path" in tool.parameters["properties"]


def test_read_document_tool_handles_missing_file(tmp_path: Path) -> None:
    out = tool.handler(path=str(tmp_path / "nope.pdf"))
    assert out.startswith("Error:")
