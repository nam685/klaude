# Installation Guide

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — Python package manager
- llama.cpp — local LLM server
- Git

## Install uv

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Clone and Install

```
git clone https://github.com/nam685/klaude.git
cd klaude
uv sync
```

`uv sync` creates a `.venv` and installs all dependencies automatically.

## Run

```
uv run klaude                   # interactive REPL
uv run klaude "fix the bug"    # one-shot mode
```

## Verify

```
uv run klaude --help
```

---

## Platform-Specific Setup

### macOS

Install llama.cpp (includes `llama-server`):

```
brew install llama.cpp
```

Apple Silicon: Metal GPU acceleration works out of the box.

Install Python 3.12 if needed:

```
brew install python@3.12
```

### Linux (Ubuntu/Debian)

Install Python:

```
sudo apt install python3.12 python3.12-venv
```

Build llama.cpp from source:

```
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp && cmake -B build && cmake --build build --config Release
```

For CUDA support, add `-DGGML_CUDA=ON` to the first cmake command:

```
cmake -B build -DGGML_CUDA=ON
```

Requires: `cmake`, `g++`, and (for CUDA) NVIDIA CUDA toolkit.

### Windows

Use WSL2 with Ubuntu, then follow the Linux instructions above. Native Windows is not tested.

---

## Dependencies

Installed automatically by `uv sync` (from `pyproject.toml`):

| Package | Version |
|---------|---------|
| openai  | >=1.60.0 |
| rich    | >=13.0.0 |
| click   | >=8.1.0  |
| mcp     | >=1.0.0  |
