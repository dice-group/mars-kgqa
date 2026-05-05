#!/bin/bash
PHASE_NAME=best_0
PRED_PATHS=(
  "processed_kgqa_ds/qald10/test"
  "processed_kgqa_ds/qald9plus/test"
)
# Reverse: move the prediction files back out
for PRED_PATH in "${PRED_PATHS[@]}"; do
  mv data_dir/${PHASE_NAME}/${PRED_PATH}/${PHASE_NAME}.prediction data_dir/${PRED_PATH}/prediction
done

# Move the non-path files back
mv data_dir/${PHASE_NAME}/${PHASE_NAME}.cluster_logs data_dir/cluster_logs
mv data_dir/${PHASE_NAME}/${PHASE_NAME}.llama-server-logs data_dir/llama-server-logs
mv data_dir/${PHASE_NAME}/${PHASE_NAME}.apptainer-config-dir data_dir/apptainer-config-dir

# Clean up empty directories (handles any number of paths)
find data_dir/${PHASE_NAME} -type d -empty -delete 2>/dev/null