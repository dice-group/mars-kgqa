#!/bin/bash
PHASE_NAME=ablation_0
PRED_PATH=processed_kgqa_ds/qald9plus/train

# Reverse: move everything back out of data_dir/ablation_0/
mv data_dir/${PHASE_NAME}/${PRED_PATH}/${PHASE_NAME}.prediction data_dir/${PRED_PATH}/prediction
mv data_dir/${PHASE_NAME}/${PHASE_NAME}.cluster_logs data_dir/cluster_logs
mv data_dir/${PHASE_NAME}/${PHASE_NAME}.llama-server-logs data_dir/llama-server-logs
mv data_dir/${PHASE_NAME}/${PHASE_NAME}.apptainer-config-dir data_dir/apptainer-config-dir

# Clean up empty directories
rmdir data_dir/${PHASE_NAME}/${PRED_PATH} 2>/dev/null
rmdir data_dir/${PHASE_NAME}/processed_kgqa_ds/qald9plus 2>/dev/null
rmdir data_dir/${PHASE_NAME}/processed_kgqa_ds 2>/dev/null
rmdir data_dir/${PHASE_NAME} 2>/dev/null