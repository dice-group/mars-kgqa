#!/bin/bash

#### Project specific vars -- start ####
export PROJECT_NAME=ag-rag-kgqa
#### Project specific vars -- end ####

# variables below this line are project agnostic

# Determine the directory of the current script
export ENV_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find the project root directory
export PROJ_ROOT_DIR="$(dirname "$ENV_SCRIPT_DIR")"

# Get the Python version in the format pyXXX 
python_version=$(python3 --version 2>&1 | awk '{split($2, v, "."); print "py" v[1] v[2]}')

export PROJ_VENV_NAME=venv_${PROJECT_NAME}_${python-version}
export PROJ_VENV_DIR=$PROJ_ROOT_DIR/$PROJ_VENV_NAME
export PROJ_DATA_DIR=$PROJ_ROOT_DIR"/data_dir"