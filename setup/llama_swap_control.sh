#!/bin/bash
set -eu

## Sample usage:
# To start on default port:   bash setup/llama_swap_control.sh start
# To start on custom port:    bash setup/llama_swap_control.sh start 9393
# To stop a specific port:    bash setup/llama_swap_control.sh stop 9393
# To restart a specific port: bash setup/llama_swap_control.sh restart 9393

CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default host port (maps to container’s 8080)
DEFAULT_PORT=9292

# Argument handling
# $1 = action (start|stop|restart); defaults to start
ACTION="${1:-start}"
# $2 = host port; defaults to $DEFAULT_PORT
HOST_PORT="${2:-$DEFAULT_PORT}"
# Container/instance name is derived from the port so each instance is unique
CONTAINER_NAME="llama-swap-$HOST_PORT"

# GPU device selection
# Use GPU_DEVICE env‑var if set; otherwise default to "all"
GPU_DEVICE="${GPU_DEVICE:-all}"

# Restart logic
if [[ "$ACTION" == "restart" ]]; then
  echo "Restarting $CONTAINER_NAME ..."
  # Stop first (will pick the correct backend)
  "$0" stop "$HOST_PORT"
  ACTION="start"
fi

# Stop logic – handles both Docker and Apptainer
if [[ "$ACTION" == "stop" ]]; then
  echo "Stopping $CONTAINER_NAME ..."
  if [[ "${SLURM_ACTIVE:-false}" == "true" ]]; then
    # Apptainer instance stop
    apptainer instance stop "$CONTAINER_NAME" || true
  else
    # Docker container stop
    docker stop "$CONTAINER_NAME"
  fi
  exit 0
fi

# Start logic – handles both Docker and Apptainer
echo "Starting $CONTAINER_NAME on host port $HOST_PORT ..."
if [[ "${SLURM_ACTIVE:-false}" == "true" ]]; then
  # Apptainer instance start (runs the startup script inside the instance)
  apptainer run --nv \
    --env LD_LIBRARY_PATH='"$LD_LIBRARY_PATH:/app"' \
    -B "$LLAMA_CACHE":/models \
    -B "$CUR_SCRIPT_DIR/llama_swap_config.yml":/app/config.yaml \
    --env LLAMA_CACHE=/models \
    --env LD_LIBRARY_PATH=/app/ \
    docker://ghcr.io/mostlygeek/llama-swap:cuda \
    --listen localhost:$HOST_PORT
else
  # Existing Docker execution
  docker run --gpus "$GPU_DEVICE" -d -it --rm --runtime nvidia \
    -p "$HOST_PORT":8080 \
    -v "$LLAMA_CACHE":/models \
    -v "$CUR_SCRIPT_DIR/llama_swap_config.yml":/app/config.yaml \
    --env LLAMA_CACHE=/models \
    --name "$CONTAINER_NAME" \
    ghcr.io/mostlygeek/llama-swap:cuda
fi