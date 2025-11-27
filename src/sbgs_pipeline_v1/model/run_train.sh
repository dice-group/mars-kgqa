#!/usr/bin/env bash
# Example wrapper to run training on GPU 0
# Usage: ./run_on_gpu.sh data.json out_dir

echo "Activating environment..."
echo "Working directory: $(pwd)"
source ../../../new_venv/bin/activate
# source new_venv/bin/activate

# pip uninstall -y torch-scatter torch-sparse torch-cluster torch-spline-conv torch-geometric

# # Then reinstall from the official PyG wheel index (use your torch+cuda version)
# pip install torch-geometric
# pip install torch-scatter -f https://data.pyg.org/whl/torch-2.5.0+cu124.html
# pip install torch-sparse -f https://data.pyg.org/whl/torch-2.5.0+cu124.html
# pip install torch-cluster -f https://data.pyg.org/whl/torch-2.5.0+cu124.html
# pip install torch-spline-conv -f https://data.pyg.org/whl/torch-2.5.0+cu124.html

# pip install -r ../../../requirements.txt


python - <<'PY'
import torch
print("PyTorch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("CUDA version:", torch.version.cuda)
print("Device count:", torch.cuda.device_count())
for i in range(torch.cuda.device_count()):
    print(f"  {i}: {torch.cuda.get_device_name(i)}")
PY

unset PYTORCH_CUDA_ALLOC_CONF

PYTORCH_CUDA_ALLOC_CONF=backend:native python - <<'PY'
import torch, torch.nn as nn
print('torch', torch.__version__, 'cuda build', torch.version.cuda, 'avail', torch.cuda.is_available())
m = nn.Linear(8, 8).to('cuda:0')
x = torch.randn(4, 8, device='cuda:0')
y = m(x)
print('OK, y:', y.shape, 'device:', y.device)
PY
# cd "$(dirname "$0")"
echo "Working directory: $(pwd)"

DATA=${1:-"../../Dataset/Tentris_train/qald9_tentris_dataset_final.json"}
OUTDIR=${2:-"./checkpoints"}
# CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}


export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export CUDA_VISIBLE_DEVICES=1
# export CUDA_VISIBLE_DEVICES=0
# export PYTHONUNBUFFERED=1

# export CUDA_VISIBLE_DEVICES
# python3 -u gnn_retriever_train.py --data "$DATA" --out_dir "$OUTDIR" --model_name "sentence-transformers/all-MiniLM-L6-v2" --batch_size 2 --epochs 8


echo "Starting GNN training on GPU..."
python gnn_retriever_train.py \
  --data "$DATA" \
  --out_dir "$OUTDIR" \
  --model_name "sentence-transformers/all-MiniLM-L6-v2" \
  --epochs 20 \
  --batch_size 4 

echo "Training completed."