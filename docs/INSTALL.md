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
