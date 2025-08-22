#!/bin/bash
set -eu

## Sample usage:
# To start: bash setup/llama_swap_control.sh start
# To stop: bash setup/llama_swap_control.sh stop
# To restart: bash setup/llama_swap_control.sh restart

# NOTE: To stop the server: docker stop llama-swap

CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# NOTE: Set $LLAMA_CACHE variable to a directory where you want the models downloaded (or have them already downloaded)

# Determine action: start by default, or based on the first argument
ACTION="${1:-start}"

# To trigger restart
if [[ "$ACTION" == "restart" ]]; then
  echo "Restarting llama-swap container..."
  # Stop the container if it exists; ignore errors if it isn’t running
  docker stop llama-swap 2>/dev/null || true
  # Continue to start the container (fall‑through to the start logic)
  ACTION="start"
fi

if [[ "$ACTION" == "stop" ]]; then
  echo "Stopping llama-swap container..."
  docker stop llama-swap
  exit 0
fi

# If we reach here, we are starting the container
# TODO: Allow variable based config for GPU assignment
echo "Starting llama-swap container..."
docker run --gpus '"device=1"' -d -it --rm --runtime nvidia -p 9292:8080 \
  -v $LLAMA_CACHE:/models \
  -v $CUR_SCRIPT_DIR/llama_swap_config.yml:/app/config.yaml \
  --env LLAMA_CACHE=/models \
  --name llama-swap \
  ghcr.io/mostlygeek/llama-swap:cuda