#!/bin/bash
set -eu
CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" # This likely gets overriden on the next 'source' call

CLUSTER_NAME=$(scontrol show config | awk -F= '/^[[:space:]]*ClusterName/ {gsub(/[[:space:]]/,"",$2); print $2}')

# Verify that the cluster‑specific directory exists
if [[ ! -d "$CUR_SCRIPT_DIR/$CLUSTER_NAME" ]]; then
  echo "Error: Directory '$CUR_SCRIPT_DIR/$CLUSTER_NAME' does not exist for cluster '$CLUSTER_NAME'." >&2
  exit 1
fi

# Module loader specific to cluster computing cluster
source "$CUR_SCRIPT_DIR/$CLUSTER_NAME/module_loader.sh"