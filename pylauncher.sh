#!/bin/bash
PY_MODULE=$2
MODE=$1

# Remove the first two arguments so "$@" now contains only the
# user‑provided options for the Python module.
shift 2

if [ "${ENV_PRELOADED:-}" != "true" ]; then
    # Determine the directory of the current script
    CUR_SCRIPT_PATH=$(realpath "$0")
    CUR_SCRIPT_DIR=$(dirname "$CUR_SCRIPT_PATH") # This will get overridden at our next source call

    # Loading environment variables (also loads slurm specific config if needed)
    source "$CUR_SCRIPT_DIR/setup/env.sh"
fi

# Environment must be loaded in the calling script
source $PROJ_VENV_DIR/bin/activate

if [ "$MODE" == "debug" ]; then
    echo "Debug mode enabled, waiting for remote debugger to attach.."
    python -u -m debugpy --wait-for-client --listen 0.0.0.0:12121 -m "$PY_MODULE" "$@"
else
    python -m "$PY_MODULE" "$@"
fi