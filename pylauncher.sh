#!/bin/bash
PY_MODULE=$1

MODE=$2

# Determine the directory of the current script
CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source $CUR_SCRIPT_DIR/setup/env.sh

source $PROJ_VENV_DIR/bin/activate

if [ "$MODE" == "debug" ]; then
    echo "Debug mode enabled, waiting for remote debugger to attach.."
    python -u -m debugpy --wait-for-client --listen 0.0.0.0:12121 -m $PY_MODULE
else
    python -m $PY_MODULE
fi