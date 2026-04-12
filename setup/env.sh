#!/bin/bash

#### Project specific vars -- start ####
export PROJECT_NAME=ag-rag-kgqa
#### Project specific vars -- end ####

# variables below this line are project agnostic

# Determine the directory of the current script
export ENV_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find the project root directory
export PROJ_ROOT_DIR="$(dirname "$ENV_SCRIPT_DIR")"

# Check if SLURM is active and source the cluster‑specific config
if [[ "${SLURM_ACTIVE:-false}" == "true" ]]; then
    source "$PROJ_ROOT_DIR/slurm/cluster_specific_config.sh" # This will load the required environment dependencies
fi

# Get the Python version in the format pyXXX 
python_version=$(python3 --version 2>&1 | awk '{split($2, v, "."); print "py" v[1] v[2]}')

export PROJ_VENV_NAME=venv_${PROJECT_NAME}_${python_version}
export PROJ_VENV_DIR=$PROJ_ROOT_DIR/$PROJ_VENV_NAME
export PROJ_DATA_DIR=$PROJ_ROOT_DIR"/data_dir"