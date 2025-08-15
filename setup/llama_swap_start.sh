#!/bin/bash

CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# NOTE: Set $LLAMA_CACHE variable to a directory where you want the models downloaded (or have them already downloaded)

docker run -it --rm --runtime nvidia -p 9292:8080 \
  -v $LLAMA_CACHE:/models \
  -v $CUR_SCRIPT_DIR/llama_swap_config.yml:/app/config.yaml \
  --env LLAMA_CACHE=/models \
  ghcr.io/mostlygeek/llama-swap:cuda 