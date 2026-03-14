#!/usr/bin/env bash
# setup-model.sh — Set up MLX model server for klaude
#
# Usage:
#   ./scripts/setup-model.sh           # install mlx-lm + download model
#   ./scripts/setup-model.sh --serve   # start the MLX server
#
# What this does:
#   1. Installs mlx-lm via uv (if not installed)
#   2. Downloads the MLX model from HuggingFace
#   3. Optionally starts mlx_lm.server

set -euo pipefail

# --- Configuration ---
MLX_MODEL="mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit"
PORT=8080

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[x]${NC} $*"; exit 1; }

# --- Serve mode ---
if [[ "${1:-}" == "--serve" ]]; then
    if ! command -v mlx_lm.server &>/dev/null; then
        error "mlx_lm not found. Run: ./scripts/setup-model.sh"
    fi
    info "Starting mlx_lm.server..."
    info "  Model: $MLX_MODEL"
    info "  Port:  $PORT"
    echo ""
    info "API will be available at: http://localhost:${PORT}/v1"
    info "Press Ctrl+C to stop"
    echo ""
    exec mlx_lm.server \
        --model "$MLX_MODEL" \
        --port "$PORT"
fi

# --- Step 1: Install mlx-lm ---
info "Step 1: Checking mlx-lm installation..."

if command -v mlx_lm.server &>/dev/null; then
    info "mlx-lm already installed"
else
    if ! command -v uv &>/dev/null; then
        error "uv not found. Install from https://docs.astral.sh/uv/"
    fi
    info "Installing mlx-lm via uv..."
    uv tool install mlx-lm
    info "Installed mlx_lm.server"
fi

echo ""

# --- Step 2: Download model ---
info "Step 2: Downloading ${MLX_MODEL}..."

# mlx_lm auto-downloads on first use, but pre-downloading avoids
# a long wait on first `--serve`. Try hf CLI, fall back to mlx_lm.generate.
if command -v hf &>/dev/null; then
    hf download "$MLX_MODEL"
elif command -v huggingface-cli &>/dev/null; then
    huggingface-cli download "$MLX_MODEL"
else
    info "Installing huggingface-hub for download..."
    uv tool install huggingface-hub
    hf download "$MLX_MODEL"
fi

echo ""
info "Setup complete!"
echo ""
info "To start the server:"
echo "  ./scripts/setup-model.sh --serve"
echo ""
info "Or manually:"
echo "  mlx_lm.server --model $MLX_MODEL --port $PORT"
echo ""
info "Then run klaude:"
echo "  uv run klaude \"your task here\""
