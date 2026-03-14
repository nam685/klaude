#!/usr/bin/env bash
# setup-model.sh — Install llama.cpp and download Qwen3-Coder-30B-A3B-Instruct
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
MODEL_REPO="unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF"
MODEL_NAME="Qwen3-Coder-30B-A3B-Instruct"
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

# Helper: find model file across common locations
find_model() {
    local quant="${1}"
    local SEARCH_DIRS=()
    for d in "$MODEL_DIR" "$HOME/Library/Caches/llama.cpp" "$HOME/.cache/llama.cpp"; do
        [[ -d "$d" ]] && SEARCH_DIRS+=("$d")
    done
    [[ ${#SEARCH_DIRS[@]} -eq 0 ]] && return
    find "${SEARCH_DIRS[@]}" \
        -name "*${MODEL_NAME}*${quant}*.gguf" ! -name "*.downloadInProgress" -type f 2>/dev/null | head -1 || true
}

# --- Serve mode ---
if [[ "${1:-}" == "--serve" ]]; then
    QUANT="${2:-Q4_K_M}"
    MODEL_FILE=$(find_model "$QUANT")
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
info "Step 2: Downloading ${MODEL_NAME} (${QUANT})..."
info "  Repository: $MODEL_REPO"
info "  Destination: $MODEL_DIR"

mkdir -p "$MODEL_DIR"

# Check if already downloaded
EXISTING=$(find_model "$QUANT")
if [[ -n "$EXISTING" ]]; then
    info "Model already downloaded: $EXISTING"
    SIZE=$(du -h "$EXISTING" | cut -f1)
    info "Size: $SIZE"
    echo ""
    info "Setup complete! To start the server:"
    echo "  ./scripts/setup-model.sh --serve"
    exit 0
fi

GGUF_FILENAME="${MODEL_NAME}-${QUANT}.gguf"
info "Downloading ${GGUF_FILENAME}..."
echo ""

MODEL_FILE=""

# Method 1: Try huggingface-cli (most reliable, handles proxies well)
if command -v huggingface-cli &>/dev/null; then
    info "Using huggingface-cli to download..."
    huggingface-cli download "$MODEL_REPO" \
        "$GGUF_FILENAME" \
        --local-dir "$MODEL_DIR"
    MODEL_FILE=$(find "$MODEL_DIR" -name "$GGUF_FILENAME" -type f 2>/dev/null | head -1)

# Method 2: Try llama-cli (built-in with llama.cpp, but proxy issues are common)
elif command -v llama-cli &>/dev/null; then
    CACHE_DIR="$HOME/Library/Caches/llama.cpp"
    [[ ! -d "$CACHE_DIR" ]] && CACHE_DIR="$HOME/.cache/llama.cpp"
    info "Using llama-cli to download from HuggingFace..."
    info "Cache: $CACHE_DIR"
    echo ""

    # Unset proxy vars that break llama-cli's HTTP client (see Note 1)
    unset ALL_PROXY all_proxy HTTPS_PROXY https_proxy HTTP_PROXY http_proxy 2>/dev/null || true

    # Run llama-cli in background so we can show download progress
    llama-cli -hf "${MODEL_REPO}:${QUANT}" -p "test" -n 1 >/dev/null 2>&1 &
    LLAMA_PID=$!

    # Poll file size to show progress while downloading
    EXPECTED_GB="18.6"
    while kill -0 "$LLAMA_PID" 2>/dev/null; do
        DL_FILE=$(find "$CACHE_DIR" -name "*${MODEL_NAME}*${QUANT}*" -type f 2>/dev/null | head -1)
        if [[ -n "$DL_FILE" ]]; then
            CURRENT_SIZE=$(stat -f%z "$DL_FILE" 2>/dev/null || stat -c%s "$DL_FILE" 2>/dev/null || echo 0)
            CURRENT_GB=$(echo "scale=1; $CURRENT_SIZE / 1073741824" | bc)
            printf "\r  Progress: %s GB / %s GB  " "$CURRENT_GB" "$EXPECTED_GB"
        fi
        sleep 2
    done
    echo ""

    wait "$LLAMA_PID" && LLAMA_OK=true || LLAMA_OK=false

    if $LLAMA_OK; then
        MODEL_FILE=$(find_model "$QUANT")
    fi

    if [[ -z "${MODEL_FILE:-}" ]]; then
        warn "llama-cli download failed. Falling back to huggingface-cli..."
    fi

# Method 3: Install huggingface-cli via uv and try again
else
    warn "No download tool found. Installing huggingface-hub..."
    uv tool install huggingface-hub
    huggingface-cli download "$MODEL_REPO" \
        "$GGUF_FILENAME" \
        --local-dir "$MODEL_DIR"
    MODEL_FILE=$(find "$MODEL_DIR" -name "$GGUF_FILENAME" -type f 2>/dev/null | head -1)
fi

# Fallback: if llama-cli failed and huggingface-cli is available, try it
if [[ -z "${MODEL_FILE:-}" ]] && command -v huggingface-cli &>/dev/null; then
    info "Retrying with huggingface-cli..."
    huggingface-cli download "$MODEL_REPO" \
        "$GGUF_FILENAME" \
        --local-dir "$MODEL_DIR"
    MODEL_FILE=$(find "$MODEL_DIR" -name "$GGUF_FILENAME" -type f 2>/dev/null | head -1)
fi

# Fallback: install huggingface-cli if nothing worked
if [[ -z "${MODEL_FILE:-}" ]] && ! command -v huggingface-cli &>/dev/null; then
    warn "Installing huggingface-hub for download..."
    uv tool install huggingface-hub
    huggingface-cli download "$MODEL_REPO" \
        "$GGUF_FILENAME" \
        --local-dir "$MODEL_DIR"
    MODEL_FILE=$(find "$MODEL_DIR" -name "$GGUF_FILENAME" -type f 2>/dev/null | head -1)
fi

echo ""

if [[ -n "${MODEL_FILE:-}" ]]; then
    info "Model downloaded: $MODEL_FILE"
    SIZE=$(du -h "$MODEL_FILE" | cut -f1)
    info "Size: $SIZE"
else
    warn "Could not locate the downloaded model file."
    warn "Try manually: huggingface-cli download $MODEL_REPO $GGUF_FILENAME --local-dir $MODEL_DIR"
fi

echo ""
info "Setup complete!"
echo ""
info "To start the server:"
echo "  ./scripts/setup-model.sh --serve"
echo ""
info "Or manually:"
echo "  llama-server -m ${MODEL_DIR}/${GGUF_FILENAME} --port ${PORT} -c ${CONTEXT_SIZE} -ngl ${GPU_LAYERS}"
echo ""
info "Then run klaude:"
echo "  uv run klaude \"your task here\""
