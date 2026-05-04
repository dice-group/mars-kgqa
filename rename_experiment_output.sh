#!/bin/bash
PHASE_NAME=ablation_0
PRED_PATH=processed_kgqa_ds/qald9plus/train

mv data_dir/apptainer-config-dir data_dir/${PHASE_NAME}.apptainer-config-dir
mv data_dir/cluster_logs data_dir/${PHASE_NAME}.cluster_logs
mv data_dir/llama-server-logs data_dir/${PHASE_NAME}.llama-server-logs
mv data_dir/${PRED_PATH}/prediction ${PRED_PATH}/${PHASE_NAME}.prediction

# Move all renamed data into data_dir/ablation_0/
mkdir -p data_dir/${PHASE_NAME}/processed_kgqa_ds/qald9plus/train

mv data_dir/${PHASE_NAME}.apptainer-config-dir data_dir/${PHASE_NAME}/
mv data_dir/${PHASE_NAME}.cluster_logs data_dir/${PHASE_NAME}/
mv data_dir/${PHASE_NAME}.llama-server-logs data_dir/${PHASE_NAME}/
mv data_dir/${PRED_PATH}/${PHASE_NAME}.prediction data_dir/${PHASE_NAME}/${PRED_PATH}/