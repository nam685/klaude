#!/usr/bin/env bash
# setup-model.sh — Install llama.cpp and download Qwen3-Coder-30B-A3B
#
# Usage:
#   ./scripts/setup-model.sh           # install + download Q4_K_M (recommended for 48GB)
#   ./scripts/setup-model.sh Q3_K_M    # download a different quantization
#   ./scripts/setup-model.sh --serve   # start the server (after downloading)
#
# What this does:
#   1. Installs llama.cpp via Homebrew (if not installed)
#   2. Downloads the GGUF model from HuggingFace
#   3. Optionally starts llama-server

set -euo pipefail

# --- Configuration ---
QUANT="${1:-Q4_K_M}"
MODEL_REPO="bartowski/Qwen3-Coder-30B-A3B-GGUF"
MODEL_DIR="$HOME/models"
CONTEXT_SIZE=32768    # 32K tokens — recommended for 48GB Mac with Q4_K_M (~24GB total)
PORT=8080
GPU_LAYERS=99         # offload everything to GPU (Apple Silicon unified memory)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
DIM='\033[0;2m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[x]${NC} $*"; exit 1; }

# --- Serve mode ---
if [[ "${1:-}" == "--serve" ]]; then
    QUANT="${2:-Q4_K_M}"
    # Search common cache locations: macOS Library/Caches, Linux ~/.cache, and MODEL_DIR
    # Build list of directories that actually exist (find fails on missing dirs,
    # and set -e + pipefail would silently kill the script)
    SEARCH_DIRS=()
    for d in "$MODEL_DIR" "$HOME/Library/Caches/llama.cpp" "$HOME/.cache/llama.cpp"; do
        [[ -d "$d" ]] && SEARCH_DIRS+=("$d")
    done
    MODEL_FILE=$(find "${SEARCH_DIRS[@]}" \
        -name "*Qwen3-Coder-30B-A3B*${QUANT}*.gguf" ! -name "*.downloadInProgress" -type f 2>/dev/null | head -1 || true)
    if [[ -z "$MODEL_FILE" ]]; then
        error "No model file found for quant $QUANT. Run setup first."
    fi
    info "Starting llama-server..."
    info "  Model: $MODEL_FILE"
    info "  Port:  $PORT"
    info "  Context: $CONTEXT_SIZE tokens"
    info "  GPU layers: $GPU_LAYERS"
    echo ""
    info "API will be available at: http://localhost:${PORT}/v1"
    info "Press Ctrl+C to stop"
    echo ""
    exec llama-server \
        -m "$MODEL_FILE" \
        --port "$PORT" \
        -c "$CONTEXT_SIZE" \
        -ngl "$GPU_LAYERS"
fi

# --- Step 1: Install llama.cpp ---
info "Step 1: Checking llama.cpp installation..."

if command -v llama-server &>/dev/null; then
    info "llama-server already installed: $(which llama-server)"
    llama-server --version 2>&1 | head -1 || true
else
    if ! command -v brew &>/dev/null; then
        error "Homebrew not found. Install from https://brew.sh"
    fi
    info "Installing llama.cpp via Homebrew..."
    brew install llama.cpp
    info "Installed: $(which llama-server)"
fi

echo ""

# --- Step 2: Download model ---
info "Step 2: Downloading Qwen3-Coder-30B-A3B (${QUANT})..."
info "  Repository: $MODEL_REPO"
info "  Destination: $MODEL_DIR"

mkdir -p "$MODEL_DIR"

# Use llama.cpp's built-in HuggingFace download
# This caches to ~/.cache/llama.cpp/ and is resumable
info "Downloading... (Q4_K_M is ~18.6GB — this will take a while)"
echo ""

# Check if we can use llama-cli for downloading, otherwise use huggingface-cli
if command -v llama-cli &>/dev/null; then
    # llama-cli can download directly with -hf flag
    # Just do a test run to trigger the download
    CACHE_DIR="$HOME/Library/Caches/llama.cpp"
    [[ ! -d "$CACHE_DIR" ]] && CACHE_DIR="$HOME/.cache/llama.cpp"
    info "Using llama-cli to download from HuggingFace..."
    info "Cache: $CACHE_DIR"
    echo ""

    # Monitor download progress in the background
    EXPECTED_SIZE=19948544000  # bytes (~18.6GB Q4_K_M)
    PARTIAL_FILE=$(find "$CACHE_DIR" -name "*${QUANT}*.downloadInProgress" -type f 2>/dev/null | head -1)

    # Start llama-cli (it handles the actual download + resume)
    # Run in background so we can show progress
    llama-cli -hf "${MODEL_REPO}:${QUANT}" -p "test" -n 1 2>/dev/null &
    LLAMA_PID=$!

    # Show progress while download is in progress
    while kill -0 "$LLAMA_PID" 2>/dev/null; do
        # Find the partial or complete file
        DL_FILE=$(find "$CACHE_DIR" -name "*${QUANT}*" -type f 2>/dev/null | head -1)
        if [[ -n "$DL_FILE" ]]; then
            CURRENT_SIZE=$(stat -f%z "$DL_FILE" 2>/dev/null || echo 0)
            PCT=$((CURRENT_SIZE * 100 / EXPECTED_SIZE))
            CURRENT_GB=$(echo "scale=1; $CURRENT_SIZE / 1073741824" | bc)
            TOTAL_GB=$(echo "scale=1; $EXPECTED_SIZE / 1073741824" | bc)
            printf "\r  Progress: %s GB / %s GB  (%d%%)" "$CURRENT_GB" "$TOTAL_GB" "$PCT"
        fi
        sleep 2
    done
    echo ""

    wait "$LLAMA_PID" || true

    # Find the cached file (macOS uses ~/Library/Caches, Linux uses ~/.cache)
    CACHE_SEARCH=()
    for d in "$HOME/Library/Caches/llama.cpp" "$HOME/.cache/llama.cpp"; do
        [[ -d "$d" ]] && CACHE_SEARCH+=("$d")
    done
    MODEL_FILE=$(find "${CACHE_SEARCH[@]}" \
        -name "*${QUANT}*.gguf" ! -name "*.downloadInProgress" -type f 2>/dev/null | head -1 || true)
elif command -v huggingface-cli &>/dev/null; then
    info "Using huggingface-cli to download..."
    huggingface-cli download "$MODEL_REPO" \
        --include "*${QUANT}*" \
        --local-dir "$MODEL_DIR"
    MODEL_FILE=$(find "$MODEL_DIR" -name "*${QUANT}*" -type f 2>/dev/null | head -1)
else
    warn "No download tool found. Installing huggingface-hub..."
    uv tool install huggingface-hub
    huggingface-cli download "$MODEL_REPO" \
        --include "*${QUANT}*" \
        --local-dir "$MODEL_DIR"
    MODEL_FILE=$(find "$MODEL_DIR" -name "*${QUANT}*" -type f 2>/dev/null | head -1)
fi

echo ""

if [[ -n "${MODEL_FILE:-}" ]]; then
    info "Model downloaded: $MODEL_FILE"
    SIZE=$(du -h "$MODEL_FILE" | cut -f1)
    info "Size: $SIZE"
else
    warn "Could not locate the downloaded model file."
    warn "Check ~/.cache/llama.cpp/ or $MODEL_DIR"
fi

echo ""
info "Setup complete!"
echo ""
info "To start the server:"
echo "  ./scripts/setup-model.sh --serve"
echo ""
info "Or manually:"
echo "  llama-server -hf ${MODEL_REPO}:${QUANT} --port ${PORT} -c ${CONTEXT_SIZE} -ngl ${GPU_LAYERS}"
echo ""
info "Then run klaude:"
echo "  uv run klaude \"your task here\""
