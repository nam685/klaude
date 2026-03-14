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

    # Check if port is already in use
    if lsof -i :"$PORT" -sTCP:LISTEN &>/dev/null; then
        PID=$(lsof -ti :"$PORT" -sTCP:LISTEN 2>/dev/null | head -1)
        PROC=$(ps -p "$PID" -o comm= 2>/dev/null || echo "unknown")
        error "Port $PORT already in use by $PROC (PID $PID). Kill it first: kill $PID"
    fi

    # Check if model is downloaded (HF cache: ~/.cache/huggingface/hub/)
    MODEL_CACHE="$HOME/.cache/huggingface/hub/models--$(echo "$MLX_MODEL" | tr '/' '--')"
    if [[ ! -d "$MODEL_CACHE" ]]; then
        warn "Model not found in cache: $MLX_MODEL"
        warn "Download it first:"
        echo ""
        echo "  ./scripts/setup-model.sh"
        echo ""
        warn "Or download manually (resumable — safe to Ctrl+C and retry):"
        echo ""
        echo "  huggingface-cli download $MLX_MODEL"
        echo ""
        exit 1
    fi

    # Check if download is complete (snapshot dir should have config.json)
    SNAPSHOT_DIR=$(find "$MODEL_CACHE/snapshots" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -1)
    if [[ -z "$SNAPSHOT_DIR" ]] || [[ ! -f "$SNAPSHOT_DIR/config.json" ]]; then
        warn "Model download appears incomplete: $MLX_MODEL"
        warn "Resume the download (picks up where it left off):"
        echo ""
        echo "  ./scripts/setup-model.sh"
        echo ""
        exit 1
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
info "Step 2: Downloading ${MLX_MODEL} (~30GB)..."
info "  This is resumable — safe to Ctrl+C and re-run to continue."
echo ""

# Ensure we have a download tool
if ! command -v hf &>/dev/null && ! command -v huggingface-cli &>/dev/null; then
    info "Installing huggingface-hub for download..."
    uv tool install huggingface-hub
fi

# Download (huggingface-cli handles resume automatically)
if command -v hf &>/dev/null; then
    hf download "$MLX_MODEL" || error "Download failed. Re-run to resume."
elif command -v huggingface-cli &>/dev/null; then
    huggingface-cli download "$MLX_MODEL" || error "Download failed. Re-run to resume."
fi

# Verify download
MODEL_CACHE="$HOME/.cache/huggingface/hub/models--$(echo "$MLX_MODEL" | tr '/' '--')"
SNAPSHOT_DIR=$(find "$MODEL_CACHE/snapshots" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -1)
if [[ -z "$SNAPSHOT_DIR" ]] || [[ ! -f "$SNAPSHOT_DIR/config.json" ]]; then
    error "Download incomplete. Re-run this script to resume."
fi

echo ""
info "Setup complete! Model cached at:"
info "  $MODEL_CACHE"
echo ""
info "To start the server:"
echo "  ./scripts/setup-model.sh --serve"
echo ""
info "Or manually:"
echo "  mlx_lm.server --model $MLX_MODEL --port $PORT"
echo ""
info "Then run klaude:"
echo "  uv run klaude \"your task here\""
