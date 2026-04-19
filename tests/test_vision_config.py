"""Tests for [vision] config parsing and api-key inheritance."""

from pathlib import Path

import pytest

from klaude.config import load_config


def _write_config(tmp_path: Path, body: str) -> Path:
    (tmp_path / ".klaude.toml").write_text(body)
    return tmp_path


def test_vision_defaults_when_missing(tmp_path: Path) -> None:
    _write_config(tmp_path, '[default]\nmodel = "local"\n')
    cfg = load_config(start_dir=str(tmp_path))
    assert cfg.vision.backend == "vlm"
    assert cfg.vision.model == "meta-llama/llama-3.2-11b-vision-instruct:free"
    assert cfg.vision.base_url == "https://openrouter.ai/api/v1"
    assert cfg.vision.fallback == "ocr"
    assert cfg.vision.api_key_env == "OPENROUTER_API_KEY"


def test_vision_section_overrides_defaults(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
[default]
model = "local"

[vision]
backend = "ocr"
model = "custom/vlm"
base_url = "https://example.com/v1"
api_key_env = "MY_KEY"
fallback = "error"
""",
    )
    cfg = load_config(start_dir=str(tmp_path))
    assert cfg.vision.backend == "ocr"
    assert cfg.vision.model == "custom/vlm"
    assert cfg.vision.base_url == "https://example.com/v1"
    assert cfg.vision.api_key_env == "MY_KEY"
    assert cfg.vision.fallback == "error"


def test_vision_inherits_api_key_from_default(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
[default]
model = "remote"
api_key_env = "PRIMARY_KEY_ENV"
""",
    )
    cfg = load_config(start_dir=str(tmp_path))
    # Would fall back to VisionConfig default ("OPENROUTER_API_KEY") if
    # inheritance wasn't wired up, so assert on the distinct value.
    assert cfg.vision.api_key_env == "PRIMARY_KEY_ENV"


def test_vision_inherits_api_key_from_profile(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
[default]
model = "local"

[profiles.remote]
model = "gpt-4o"
api_key_env = "OPENAI_API_KEY"
""",
    )
    cfg = load_config(start_dir=str(tmp_path), profile="remote")
    assert cfg.vision.api_key_env == "OPENAI_API_KEY"


def test_vision_explicit_overrides_inheritance(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
[default]
model = "remote"
api_key_env = "OPENROUTER_API_KEY"

[vision]
api_key_env = "MY_VISION_KEY"
""",
    )
    cfg = load_config(start_dir=str(tmp_path))
    assert cfg.vision.api_key_env == "MY_VISION_KEY"


def test_vision_invalid_backend_raises(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
[default]
model = "local"

[vision]
backend = "nope"
""",
    )
    with pytest.raises(ValueError, match="vision.backend"):
        load_config(start_dir=str(tmp_path))


def test_vision_invalid_fallback_raises(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
[default]
model = "local"

[vision]
fallback = "retry"
""",
    )
    with pytest.raises(ValueError, match="vision.fallback"):
        load_config(start_dir=str(tmp_path))
