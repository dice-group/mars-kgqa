#!/bin/bash

## Sample usage: bash execute_experiment.sh --gpu 0,1 --approach PBSG_2HOP --dataset QALD9PLUS_UPDATED_CURWD --split TEST --llm GEMMA3

set -euo pipefail


# Helper: print usage
usage() {
  cat <<EOF
Usage: $0 [OPTIONS] --approach <APPROACH> --dataset <DATASET> --split <SPLIT> --llm <LLM> [--use-gold]

Options:
  --gpu <ID|all>          GPU device to expose to llama‑swap (default: all)
  --port <PORT>           Host port for llama‑swap (default: random 9200‑9300)
  --debug                 Run run.py under debugpy (adds remote‑debug support)
  -h, --help              Show this help message
EOF
  exit 1
}


# Default values
GPU_DEVICE="all"
PORT=""
MODE="run"   # normal execution; can be changed to "debug" via --debug
USE_GOLD="false"


# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpu)       GPU_DEVICE="${2:?Missing value for --gpu}"; shift 2 ;;
    --port)      PORT="${2:?Missing value for --port}"; shift 2 ;;
    --debug)     MODE="debug"; shift ;;
    --use-gold)  USE_GOLD="true"; shift ;;
    --approach)  APPROACH="${2:?Missing value for --approach}"; shift 2 ;;
    --dataset)   DATASET="${2:?Missing value for --dataset}"; shift 2 ;;
    --split)     SPLIT="${2:?Missing value for --split}"; shift 2 ;;
    --llm)       LLM="${2:?Missing value for --llm}"; shift 2 ;;
    -h|--help)   usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

# Adjusting GPU value for llama-swap's docker container
if [[ "$GPU_DEVICE" != "all" && "$GPU_DEVICE" != \"device=*\" ]]; then
  GPU_DEVICE="\"device=${GPU_DEVICE}\""
fi


# Validate required args
[[ -z "${APPROACH:-}" ]] && { echo "Error: --approach is required"; usage; }
[[ -z "${DATASET:-}"  ]] && { echo "Error: --dataset is required";  usage; }
[[ -z "${SPLIT:-}"    ]] && { echo "Error: --split is required";    usage; }
[[ -z "${LLM:-}"      ]] && { echo "Error: --llm is required";      usage; }


# Choose a free port if none supplied
if [[ -z "$PORT" ]]; then
  # Try up to 10 times to find an unused port in the 9200‑9300 range
  for i in {1..10}; do
    PORT=$(shuf -i 9200-9300 -n 1)
    if ! ss -ltnp | grep -q ":$PORT "; then
      break
    fi
    PORT=""
  done
  : ${PORT:?"Failed to find a free port in 9200‑9300"}
fi


# Export GPU selection for llama‑swap
export GPU_DEVICE

# Start llama‑swap container (and ensure it stops on script exit)
CONTAINER_NAME="llama-swap-$PORT"
bash setup/llama_swap_control.sh start "$PORT"

# Register a trap to stop the container when the script exits or is interrupted
cleanup() {
  echo "Cleaning up processes..."
  # Prevent the trap from firing again (e.g., when EXIT follows INT)
  trap - EXIT INT TERM

  # Try to stop the container, but ignore “not found” errors
  bash setup/llama_swap_control.sh stop "$PORT" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Give the server a moment to start up
echo "Waiting for llama‑swap to become reachable..."
for i in {1..10}; do
  if curl -s "http://127.0.0.1:$PORT/v1/models" > /dev/null 2>&1; then
    echo "Llama‑swap is up."
    break
  fi
  sleep 1
done


# Export the OpenAI‑compatible endpoint for the rest of the code
export LLAMA_SWAP_OPENAI_ENDPOINT="http://127.0.0.1:${PORT}/v1"


# Build the argument list for run.py
RUN_ARGS=(
  --approach   "$APPROACH"
  --dataset    "$DATASET"
  --split      "$SPLIT"
  --llm        "$LLM"
)

if [[ "$USE_GOLD" == "true" ]]; then
  RUN_ARGS+=(--use-gold)
fi


# Calling run.py through the pylauncher helper
echo "Launching experiment via pylauncher.sh ($MODE)..."
bash pylauncher.sh "$MODE" src.run "${RUN_ARGS[@]}"


# End of script – the trap will stop the container automatically
