#!/bin/bash
# Restore prediction data and logs from a phase directory back to the top level.
# Usage: bash rollback_rename_changes.sh [--dry-run]
set -euo pipefail

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
fi

PHASE_NAME=ablation_1
PRED_PATHS=(
  "processed_kgqa_ds/qald9plus/train"
)
STATIC_ITEMS=(
  "cluster_logs"
  "llama-server-logs"
  "apptainer-config-dir"
)

if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] Would restore from data_dir/${PHASE_NAME}/"
else
  echo "==> Restoring from data_dir/${PHASE_NAME}/"
fi

# Move prediction directories back
for PRED_PATH in "${PRED_PATHS[@]}"; do
  src="data_dir/${PHASE_NAME}/${PRED_PATH}/prediction"
  dest="data_dir/${PRED_PATH}/prediction"
  if [ -e "${src}" ]; then
    if [ "$DRY_RUN" = true ]; then
      echo "[DRY RUN] Would create dir: data_dir/${PRED_PATH}/"
      echo "[DRY RUN] Would move: ${src} -> ${dest}"
    else
      mkdir -p "data_dir/${PRED_PATH}/"
      mv "${src}" "${dest}"
      echo "  moved: ${PRED_PATH}/prediction"
    fi
  else
    echo "  skip  : ${PRED_PATH}/prediction (not found)" >&2
  fi
done

# Move static items back
for item in "${STATIC_ITEMS[@]}"; do
  src="data_dir/${PHASE_NAME}/${item}"
  dest="data_dir/${item}"
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

# Clean up empty phase directory and any leftover subdirectories
if [ -d "data_dir/${PHASE_NAME}" ]; then
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would clean: data_dir/${PHASE_NAME}/ (remove empty dirs)"
  else
    find "data_dir/${PHASE_NAME}" -type d -empty -delete 2>/dev/null || true
    echo "  cleaned: data_dir/${PHASE_NAME}/ (empty dirs removed)"
  fi
fi

if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] Done."
else
  echo "==> Done."
fi
