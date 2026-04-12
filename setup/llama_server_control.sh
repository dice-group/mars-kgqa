#!/bin/bash
set -eu

## Sample usage:
# To start on default port:   bash setup/llama_server_control.sh start
# To start on custom port:    bash setup/llama_server_control.sh start 9393
# To stop a specific port:    bash setup/llama_server_control.sh stop 9393
# To restart a specific port: bash setup/llama_server_control.sh restart 9393

CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default host port (maps to container’s 8080)
DEFAULT_PORT=9292

# Argument handling
# $1 = action (start|stop|restart); defaults to start
ACTION="${1:-start}"
# $2 = host port; defaults to $DEFAULT_PORT
HOST_PORT="${2:-$DEFAULT_PORT}"
# Container/instance name is derived from the port so each instance is unique
CONTAINER_NAME="llama-server-$HOST_PORT"

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

# TODO: Improve the hacky solution for apptainer deployment
# Define where we keep the background PID for each port
LOG_DIR="data_dir/llama-server-logs"

mkdir -p $LOG_DIR

TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"

PID_FILE="${LOG_DIR}/llama-server-${HOST_PORT}.pid"
LOG_FILE="${LOG_DIR}/llama-server-${HOST_PORT}-${TIMESTAMP}.log"

# Stop logic – handles both Docker and Apptainer
if [[ "$ACTION" == "stop" ]]; then
  echo "Stopping $CONTAINER_NAME ..."
  if [[ "${SLURM_ACTIVE:-false}" == "true" ]]; then
    # Apptainer: kill the background process started with `run`
    if [[ -f "$PID_FILE" ]]; then
      kill -TERM "$(cat "$PID_FILE")" && rm -f "$PID_FILE"
      echo "Apptainer process stopped."
    else
      echo "No PID file found; nothing to stop."
    fi
  else
    docker stop "$CONTAINER_NAME"
  fi
  exit 0
fi

# Start logic – handles both Docker and Apptainer
echo "Starting $CONTAINER_NAME on host port $HOST_PORT ..."
if [[ "${SLURM_ACTIVE:-false}" == "true" ]]; then
  mkdir -p $LOG_DIR
  # NOTE: Build the apptainer SIF from OCI beforehand
  # Apptainer run in background via nohup; capture its PID
  nohup apptainer run --nv \
    --env LD_LIBRARY_PATH='"$LD_LIBRARY_PATH:/app"' \
    -B "$LLAMA_CACHE":/models \
    -B "$CUR_SCRIPT_DIR/llama_server_models.ini":/app/models.ini \
    --env LLAMA_CACHE=/models \
    --env LD_LIBRARY_PATH=/app/ \
    llama-server_cuda.sif \
    --listen localhost:$HOST_PORT \
    --models-preset /app/models.ini --host 0.0.0.0 --port 8080 --models-max 2 --parallel 1 \
    >"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
else
  docker run --gpus all -d -it --rm \
    -p "$HOST_PORT":8080 \
    -v "$LLAMA_CACHE":/models \
    -v "$CUR_SCRIPT_DIR/llama_server_models.ini":/app/models.ini \
    --env LLAMA_CACHE=/models \
    --env LLAMA_SET_ROWS=1 \
    --name "$CONTAINER_NAME" \
    ghcr.io/ggml-org/llama.cpp:server-cuda13-b8763 \
    --models-preset /app/models.ini --host 0.0.0.0 --port 8080 --models-max 2 --parallel 1
fi
