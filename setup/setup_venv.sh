#!/bin/bash
set -eu

# Determine the directory of the current script
CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # This gets overriden on the next 'source' call
SETUP_DIR=$CUR_SCRIPT_DIR

source $SETUP_DIR/env.sh

# Creating directory for huggingface cache
#mkdir -p $HF_HOME

# Tested with python 3.12.3
python -m venv $PROJ_VENV_DIR
source $PROJ_VENV_DIR/bin/activate

export TMPDIR="${SETUP_DIR}/../.tmp"
mkdir $TMPDIR

pip install --no-cache-dir -r $SETUP_DIR/requirements.txt

ipython kernel install --user --name=$PROJ_VENV_NAME

echo "Setup finished. Python virtual environment can be found at: "$PROJ_VENV_DIR