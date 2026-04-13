#!/bin/bash
set -eu

## Sample usage:
# To start on default port:   bash setup/llama_server_control.sh start
# To start on custom port:    bash setup/llama_server_control.sh start 9393
# To stop a specific port:    bash setup/llama_server_control.sh stop 9393
# To restart a specific port: bash setup/llama_server_control.sh restart 9393

CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default host port (maps to container's 8080)
DEFAULT_PORT=9292

# Argument handling
# $1 = action (start|stop|restart); defaults to start
ACTION="${1:-start}"
# $2 = host port; defaults to $DEFAULT_PORT
HOST_PORT="${2:-$DEFAULT_PORT}"
# Container/instance name is derived from the port so each instance is unique
LLAMA_CONTAINER_NAME="llama-server-$HOST_PORT"

LLAMA_ARG_CTX_SIZE="${LLAMA_CTX:-49152}"

# GPU device selection
# Use GPU_DEVICE env‑var if set; otherwise default to "all"
GPU_DEVICE="${GPU_DEVICE:-all}"

# Max restart attempts on failure
MAX_RETRIES="${MAX_RETRIES:-50}"

# Restart logic
if [[ "$ACTION" == "restart" ]]; then
  echo "Restarting $LLAMA_CONTAINER_NAME ..."
  # Stop first (will pick the correct backend)
  "$0" stop "$HOST_PORT"
  ACTION="start"
fi

# TODO: Improve the hacky solution for apptainer deployment
# Define where we keep the background PID for each port
LOG_DIR="data_dir/llama-server-logs"

mkdir -p $LOG_DIR

TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"

PID_FILE="${LOG_DIR}/llama-server-${HOST_PORT}-${TIMESTAMP}.pid"
LOG_FILE="${LOG_DIR}/llama-server-${HOST_PORT}-${TIMESTAMP}.log"

# Stop logic – handles both Docker and Apptainer
if [[ "$ACTION" == "stop" ]]; then
  echo "Stopping $LLAMA_CONTAINER_NAME ..."
  if [[ "${SLURM_ACTIVE:-false}" == "true" ]]; then
    # Apptainer: kill the background process started with `run`
    if [[ "${SLURM_ACTIVE:-false}" == "true" ]]; then
      apptainer instance stop "$LLAMA_CONTAINER_NAME" 2>/dev/null || true
      echo "Apptainer instance stopped."
    else
      echo "No PID file found; nothing to stop."
    fi
  else
    docker stop "$LLAMA_CONTAINER_NAME"
  fi
  exit 0
fi

# Start logic – handles both Docker and Apptainer
echo "Starting $LLAMA_CONTAINER_NAME on host port $HOST_PORT ..."
if [[ "${SLURM_ACTIVE:-false}" == "true" ]]; then
  mkdir -p $LOG_DIR
  # NOTE: Build the apptainer SIF from OCI beforehand
  # Apptainer run in background via nohup with a restart-on-failure wrapper
  (
    attempt=0
    while [ $attempt -lt "$MAX_RETRIES" ]; do
      apptainer instance start --nv \
        --env LD_LIBRARY_PATH="$LD_LIBRARY_PATH:/app" \
        -B "$LLAMA_CACHE":/models \
        -B "$CUR_SCRIPT_DIR/llama_server_models.ini":/app/models.ini \
        --env LLAMA_CACHE=/models \
        --env LLAMA_SET_ROWS=1 \
        --env LD_LIBRARY_PATH=/app/ \
        llama-server_cuda.sif \
        "$LLAMA_CONTAINER_NAME" \
        --listen localhost:"$HOST_PORT" \
        --models-preset /app/models.ini --host 0.0.0.0 --port 8080 --models-max 2 --parallel 1 --ctx-size "$LLAMA_ARG_CTX_SIZE"

      # Wait for the instance to finish
      apptainer instance list | grep -q "$LLAMA_CONTAINER_NAME" && \
        tail --pid=$(apptainer instance list | awk "/$LLAMA_CONTAINER_NAME/ {print \$2}") -f /dev/null

      exit_code=$?
      [ $exit_code -eq 0 ] && break

      attempt=$((attempt + 1))
      echo "[$(date)] Instance exited with code $exit_code. Retry $attempt/$MAX_RETRIES..." | tee -a "$LOG_FILE"
      apptainer instance stop "$LLAMA_CONTAINER_NAME" 2>/dev/null || true
      sleep 2
    done

    if [ $attempt -ge "$MAX_RETRIES" ]; then
      echo "[$(date)] All $MAX_RETRIES retries exhausted. Giving up." | tee -a "$LOG_FILE"
      exit 1
    fi
  ) >> "$LOG_FILE" 2>&1 &

  echo $! > "$PID_FILE"
else
  run_container() {
    docker rm -f "$LLAMA_CONTAINER_NAME" 2>/dev/null || true
    docker run --gpus $GPU_DEVICE -d -it \
      -p "$HOST_PORT":8080 \
      -v "$LLAMA_CACHE":/models \
      -v "$CUR_SCRIPT_DIR/llama_server_models.ini":/app/models.ini \
      --env LLAMA_CACHE=/models \
      --env LLAMA_SET_ROWS=1 \
      --name "$LLAMA_CONTAINER_NAME" \
      ghcr.io/ggml-org/llama.cpp:server-cuda13-b8763 \
      --models-preset /app/models.ini --host 0.0.0.0 --port 8080 --models-max 2 --parallel 1 --ctx-size "$LLAMA_ARG_CTX_SIZE"
  }

  (
    attempt=0
    while [ "$attempt" -lt "$MAX_RETRIES" ]; do
      run_container
      exit_code=$(docker wait "$LLAMA_CONTAINER_NAME")

      [ "$exit_code" -eq 0 ] && break

      attempt=$(( attempt + 1 ))
      echo "[$(date)] Container exited with code $exit_code. Retry $attempt/$MAX_RETRIES..." | tee -a "$LOG_FILE"
      sleep 2
    done

    if [ "$attempt" -ge "$MAX_RETRIES" ]; then
      echo "[$(date)] All $MAX_RETRIES retries exhausted. Giving up." | tee -a "$LOG_FILE"
    fi
  ) >> "$LOG_FILE" 2>&1 &

  echo $! > "$PID_FILE"
fi