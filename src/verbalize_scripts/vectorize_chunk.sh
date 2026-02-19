#!/usr/bin/env bash
set -euo pipefail

## Sample usage: bash src/verbalize_scripts/vectorize_chunk.sh data_dir/verbalization/2000_chunks/dataset_chunk_0107.txt data_dir/verbalization/2000_chunks/

# Default mode (run) – can be overridden with --debug
MODE="normal"

# Positional arguments: <chunk_file> <out_dir>
# Options: --debug
while [[ $# -gt 0 ]]; do
  case "$1" in
    --debug) MODE="debug"; shift ;;          # switch to debug mode
    -h|--help)
      echo "Usage: $0 [--debug] <chunk_file> <out_dir>"
      exit 0
      ;;
    --*) echo "Warning: unknown option '$1' ignored"; shift ;;
    *)  # first non‑option argument -> CHUNK_FILE, second -> OUT_DIR
      if [[ -z "${CHUNK_FILE:-}" ]]; then
        CHUNK_FILE="$1"
      elif [[ -z "${OUT_DIR:-}" ]]; then
        OUT_DIR="$1"
      else
        echo "Warning: extra argument '$1' ignored"
      fi
      shift
      ;;
  esac
done

# Validate required arguments
if [[ -z "${CHUNK_FILE:-}" || -z "${OUT_DIR:-}" ]]; then
  echo "Error: missing required arguments."
  echo "Usage: $0 [--debug] <chunk_file> <out_dir>"
  exit 1
fi

CHUNK_FILE="$(realpath "$CHUNK_FILE")"
OUT_DIR="$(realpath "$OUT_DIR")"
mkdir -p "$OUT_DIR"

# Load shared environment (same as execute_experiment.sh)
PROJ_ROOT="./"
source "$PROJ_ROOT/setup/env.sh"
export ENV_PRELOADED=true
export RUN_SYS_NAME="${CLUSTER_NAME:-$(hostname)}"

GPU_DEVICE="all"; export GPU_DEVICE            # expose all GPUs by default

# Start llama‑swap on a free port
PORT=$(shuf -i 10000-11000 -n 1)
while ss -ltnp | grep -q ":$PORT "; do PORT=$(shuf -i 10000-11000 -n 1); done
bash "$PROJ_ROOT/setup/llama_swap_control.sh" start "$PORT"

# Ensure container stops on exit / interrupt
cleanup() { trap - EXIT INT TERM; bash "$PROJ_ROOT/setup/llama_swap_control.sh" stop "$PORT" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

# Wait until llama‑swap is reachable (max 60 s)
for i in {1..60}; do
  if curl -s "http://127.0.0.1:$PORT/v1/models" > /dev/null 2>&1; then break; fi
  sleep 1
done

export LLAMA_SWAP_OPENAI_ENDPOINT="http://127.0.0.1:${PORT}/v1"   # endpoint for Python code

# Build arguments for the vectorizer
RUN_ARGS=($CHUNK_FILE $OUT_DIR)

# Launch via pylauncher.sh using the chosen mode (run/debug)
echo "Launching vectorization (mode=$MODE)…"
bash "$PROJ_ROOT/pylauncher.sh" "$MODE" src.verbalize_scripts.vectorize_chunk "${RUN_ARGS[@]}"

# Trap (cleanup) will stop the container automatically