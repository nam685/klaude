# Installation Guide

## Quick Install (recommended)

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install klaude globally
uv tool install git+ssh://git@github.com/nam685/klaude.git
```

Done. Run `klaude` from any directory.

## Update

```bash
uv tool install --force git+ssh://git@github.com/nam685/klaude.git
```

## Development Install (clone)

If you want to hack on klaude itself:

```bash
git clone git@github.com:nam685/klaude.git
cd klaude
uv sync
uv run klaude --help
```

## Verify

```bash
klaude --help
```

## Model Setup

klaude needs a local LLM server. See [SETUP-MODEL.md](SETUP-MODEL.md) for
downloading the model and starting the server.

Quick version (macOS with Apple Silicon):

```bash
# Install mlx-lm and download the model
./scripts/setup-model.sh

# Start the server
./scripts/setup-model.sh --serve

# In another terminal
klaude "hello, list the files here"
```

## Prerequisites

- macOS (Apple Silicon) or Linux
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Dependencies

Installed automatically:

| Package | Purpose |
|---------|---------|
| openai  | LLM API client (OpenAI-compatible) |
| rich    | Terminal formatting, syntax highlighting |
| click   | CLI argument parsing |
| mcp     | Model Context Protocol support |

## Optional system tools (for `read_document`)

klaude's `read_document` tool shells out to system binaries for PDFs and
images. They are **not** auto-installed; install them if you plan to read
those formats:

- **`poppler`** — provides `pdftotext`, needed for PDF extraction.
  - macOS: `brew install poppler`
  - Debian/Ubuntu: `sudo apt install poppler-utils`
- **`tesseract`** — needed for image OCR (the fallback when no VLM is
  configured).
  - macOS: `brew install tesseract`
  - Debian/Ubuntu: `sudo apt install tesseract-ocr`

For VLM-based image descriptions instead of OCR, export
`OPENROUTER_API_KEY` and configure the `[vision]` block in
`.klaude.toml`. See `USAGE.md`.
