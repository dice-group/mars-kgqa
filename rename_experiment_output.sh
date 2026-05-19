#!/bin/bash
# Archive prediction data and logs into a phase directory.
# Usage: bash rename_experiment_output.sh [--dry-run]
set -euo pipefail

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
fi

PHASE_NAME=ssg_1
PRED_PATHS=(
  #"processed_kgqa_ds/qald10/test"
  #"processed_kgqa_ds/qald9plus/test"
  #"processed_kgqa_ds/lcquad2/test"
  "processed_kgqa_ds/qald9plus/train"
)
STATIC_ITEMS=(
  "cluster_logs"
  "llama-server-logs"
  "apptainer-config-dir"
)

if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] Would archive into data_dir/${PHASE_NAME}/"
else
  echo "==> Archiving into data_dir/${PHASE_NAME}/"
  mkdir -p "data_dir/${PHASE_NAME}/"
fi

# Move static items (logs, config dirs)
for item in "${STATIC_ITEMS[@]}"; do
  src="data_dir/${item}"
  dest="data_dir/${PHASE_NAME}/${item}"
  if [ -e "${src}" ]; then
    if [ "$DRY_RUN" = true ]; then
      echo "[DRY RUN] Would move: ${src} -> ${dest}"
    else
      mv "${src}" "${dest}"
      echo "  moved: ${item}"
    fi
  else
    echo "  skip  : ${item} (not found)" >&2
  fi
done

# Move prediction directories
for PRED_PATH in "${PRED_PATHS[@]}"; do
  src="data_dir/${PRED_PATH}/prediction"
  dest="data_dir/${PHASE_NAME}/${PRED_PATH}/prediction"
  if [ -e "${src}" ]; then
    if [ "$DRY_RUN" = true ]; then
      echo "[DRY RUN] Would create dir: data_dir/${PHASE_NAME}/${PRED_PATH}/"
      echo "[DRY RUN] Would move: ${src} -> ${dest}"
    else
      mkdir -p "data_dir/${PHASE_NAME}/${PRED_PATH}/"
      mv "${src}" "${dest}"
      echo "  moved: ${PRED_PATH}/prediction"
    fi
  else
    echo "  skip  : ${PRED_PATH}/prediction (not found)" >&2
  fi
done

if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] Done."
else
  echo "==> Done."
fi
