#!/bin/bash
PHASE_NAME=best_0
PRED_PATHS=(
  "processed_kgqa_ds/qald10/test"
  "processed_kgqa_ds/qald9plus/test"
)

mv data_dir/apptainer-config-dir data_dir/${PHASE_NAME}.apptainer-config-dir
mv data_dir/cluster_logs data_dir/${PHASE_NAME}.cluster_logs
mv data_dir/llama-server-logs data_dir/${PHASE_NAME}.llama-server-logs

# Move all renamed data into data_dir/ablation_0/
mkdir -p data_dir/${PHASE_NAME}/

mv data_dir/${PHASE_NAME}.apptainer-config-dir data_dir/${PHASE_NAME}/
mv data_dir/${PHASE_NAME}.cluster_logs data_dir/${PHASE_NAME}/
mv data_dir/${PHASE_NAME}.llama-server-logs data_dir/${PHASE_NAME}/

# Loop over each prediction path
for PRED_PATH in "${PRED_PATHS[@]}"; do
  mkdir -p data_dir/${PHASE_NAME}/${PRED_PATH}/
  mv data_dir/${PRED_PATH}/prediction data_dir/${PHASE_NAME}/${PRED_PATH}/prediction
done