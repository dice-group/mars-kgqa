#!/bin/bash
PY_MODULE=$2
MODE=$1

# Determine the directory of the current script
CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source $CUR_SCRIPT_DIR/setup/env.sh
source $PROJ_VENV_DIR/bin/activate

# Capture any additional CLI arguments
EXTRA_ARGS="${@:3}"

if [ "$MODE" == "debug" ]; then
    echo "Debug mode enabled, waiting for remote debugger to attach.."
    python -u -m debugpy --wait-for-client --listen 0.0.0.0:12121 -m $PY_MODULE $EXTRA_ARGS
else
    python -m $PY_MODULE $EXTRA_ARGS
fi