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
# Use GPU_DEVICE env-var if set; otherwise default to "all"
GPU_DEVICE="${GPU_DEVICE:-all}"

# Max restart attempts on failure
MAX_RETRIES="${MAX_RETRIES:-50}"

# Restart logic
if [[ "$ACTION" == "restart" ]]; then
  echo "Restarting $LLAMA_CONTAINER_NAME ..."
  "$0" stop "$HOST_PORT"
  ACTION="start"
fi

# Define where we keep logs for each port
JOB_ID=${SLURM_JOB_ID:-}
LOG_DIR="data_dir/llama-server-logs/${JOB_ID}"
mkdir -p "$LOG_DIR"

MACHINE_NAME="${RUN_SYS_NAME:-$(hostname)}"

TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"
PID_FILE="${LOG_DIR}/llama-server-${HOST_PORT}-${MACHINE_NAME}.pid"
LOG_FILE="${LOG_DIR}/llama-server-${HOST_PORT}--${MACHINE_NAME}-${TIMESTAMP}.log"
SENTINEL_FILE="${LOG_DIR}/llama-server-${HOST_PORT}-${MACHINE_NAME}.stop"

# Stop logic
if [[ "$ACTION" == "stop" ]]; then
  echo "Stopping $LLAMA_CONTAINER_NAME ..."
  if [[ "${SLURM_ACTIVE:-false}" == "true" ]]; then
    touch "$SENTINEL_FILE"   # Signal to the retry loop: don't restart
    apptainer instance stop "$LLAMA_CONTAINER_NAME" 2>/dev/null || true
    echo "Apptainer instance stopped."
  else
    docker stop "$LLAMA_CONTAINER_NAME"
  fi
  if [ -f "$PID_FILE" ]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    rm -f "$PID_FILE"
  fi
  exit 0
fi

## Important Note: We are running the containers in way that they will be restarted if they were forced to exit from our python script. We do this because llama-server has an issue where it repeatedly throws Internal Server Error for certain inputs (maybe because: https://github.com/ggml-org/llama.cpp/issues/21289) and then any request to that LLM will fail afterwards. However, it does not shutdown the container on its own, so we have to do it manually and then restart it.

# Start logic
echo "Starting $LLAMA_CONTAINER_NAME on host port $HOST_PORT ..."
rm -f "$SENTINEL_FILE"

if [[ "${SLURM_ACTIVE:-false}" == "true" ]]; then
  export APPTAINER_CONFIGDIR="data_dir/apptainer-config-dir/${JOB_ID}"
  mkdir -p "$APPTAINER_CONFIGDIR"
  # NOTE: Build the apptainer SIF from OCI beforehand: "apptainer build llama-cpp-server.sif docker://ghcr.io/ggml-org/llama.cpp:server-cuda13-b8763"
  # Use `apptainer instance run` so the container's runscript (entrypoint) is
  # executed, not the startscript. Arguments after the instance name are
  # forwarded to the runscript.
  (
    attempt=0
    while [ "$attempt" -lt "$MAX_RETRIES" ]; do
      apptainer instance run --nv \
        --env LD_LIBRARY_PATH="$LD_LIBRARY_PATH:/app" \
        -B "$LLAMA_CACHE":/models \
        -B "$CUR_SCRIPT_DIR/llama_server_models.ini":/app/models.ini \
        --env LLAMA_CACHE=/models \
        --env LLAMA_SET_ROWS=1 \
        llama-cpp-server-cuda12-b8763.sif \
        "$LLAMA_CONTAINER_NAME" \
        --models-preset /app/models.ini --host 0.0.0.0 --port $HOST_PORT --models-max 2 --parallel 1 --ctx-size "$LLAMA_ARG_CTX_SIZE" --verbose --sleep-idle-seconds 600

      # Poll until the instance disappears
      while apptainer instance list | grep -q "$LLAMA_CONTAINER_NAME"; do
        sleep 5
      done

      apptainer instance stop "$LLAMA_CONTAINER_NAME" 2>/dev/null || true

      if [ -f "$SENTINEL_FILE" ]; then
        echo "[$(date)] Sentinel found — intentional stop, not restarting." | tee -a "$LOG_FILE"
        rm -f "$SENTINEL_FILE"
        exit 0
      fi

      attempt=$(( attempt + 1 ))
      echo "[$(date)] Instance exited unexpectedly. Retry $attempt/$MAX_RETRIES..." | tee -a "$LOG_FILE"
      sleep 2
    done

    echo "[$(date)] All $MAX_RETRIES retries exhausted. Giving up." | tee -a "$LOG_FILE"
    exit 1
  ) >> "$LOG_FILE" 2>&1 &

  echo $! > "$PID_FILE"

else
  run_container() {
    docker rm -f "$LLAMA_CONTAINER_NAME" 2>/dev/null || true
    docker run --gpus "$GPU_DEVICE" -d -it \
      -p "$HOST_PORT":8080 \
      -v "$LLAMA_CACHE":/models \
      -v "$CUR_SCRIPT_DIR/llama_server_models.ini":/app/models.ini \
      --env LLAMA_CACHE=/models \
      --env LLAMA_SET_ROWS=1 \
      --name "$LLAMA_CONTAINER_NAME" \
      ghcr.io/ggml-org/llama.cpp:server-cuda12-b8562 \
      --models-preset /app/models.ini --host 0.0.0.0 --port 8080 --models-max 2 --parallel 1 --ctx-size "$LLAMA_ARG_CTX_SIZE" --sleep-idle-seconds 600
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