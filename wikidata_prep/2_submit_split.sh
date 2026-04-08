#!/bin/bash
#============================================================================
# 2_submit_split.sh — Phase 2: Submit the SLURM array job to classify chunks.
#
# Usage:
#   ./2_submit_split.sh <output_dir> [config.yaml]
#
# Example:
#   ./2_submit_split.sh /scratch/wd_split
#   ./2_submit_split.sh /scratch/wd_split wdqs-subgraph-definitions-v2.yaml
#
# Expects chunks from phase 1 in <output_dir>/chunks/
# Writes partial results to <output_dir>/split_out/
#============================================================================
set -euo pipefail

CUR_SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" 

# Loading environment variables
source "$CUR_SCRIPT_DIR/../setup/env.sh"
# Environment must be loaded in the calling script
source $PROJ_VENV_DIR/bin/activate

OUTDIR="${1:?Usage: $0 <output_dir> [config.yaml]}"
CONFIG="${2:-}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHUNK_DIR="${OUTDIR}/chunks"
SPLIT_DIR="${OUTDIR}/split_out"
LOG_DIR="${OUTDIR}/logs"

mkdir -p "$SPLIT_DIR" "$LOG_DIR"

# Count chunks
ACTUAL_CHUNKS=$(ls "${CHUNK_DIR}"/chunk_*.nt.zst 2>/dev/null | wc -l)
if [ "$ACTUAL_CHUNKS" -eq 0 ]; then
    ACTUAL_CHUNKS=$(ls "${CHUNK_DIR}"/chunk_*.nt 2>/dev/null | wc -l)
fi

if [ "$ACTUAL_CHUNKS" -eq 0 ]; then
    echo "ERROR: No chunk files found in $CHUNK_DIR"
    echo "       Run phase 1 first: ./1_submit_presplit.sh <input> $OUTDIR"
    exit 1
fi

MAX_IDX=$((ACTUAL_CHUNKS - 1))

echo "Phase 2: Classify chunks"
echo "  Chunk dir:  $CHUNK_DIR"
echo "  Split dir:  $SPLIT_DIR"
echo "  Chunks:     $ACTUAL_CHUNKS (array 0-$MAX_IDX)"
if [ -n "$CONFIG" ]; then
    CONFIG_ABS="$(cd "$(dirname "$CONFIG")" && pwd)/$(basename "$CONFIG")"
    echo "  Config:     $CONFIG_ABS"
else
    CONFIG_ABS=""
    echo "  Config:     built-in v2 defaults"
fi
echo ""

# Build the --config flag for the worker
CONFIG_FLAG=""
if [ -n "$CONFIG_ABS" ]; then
    CONFIG_FLAG="--config ${CONFIG_ABS}"
fi

JOB_ID=$(sbatch --parsable <<SBATCH
#!/bin/bash
#SBATCH --job-name=wd-split
#SBATCH --array=0-${MAX_IDX}%50
#SBATCH --cpus-per-task=2
#SBATCH --mem=12G
#SBATCH --time=04:00:00
#SBATCH --output=${LOG_DIR}/split_%a.out
#SBATCH --error=${LOG_DIR}/split_%a.err

set -euo pipefail

python3 "${SCRIPT_DIR}/wikidata_split_worker.py" \
    --chunk-dir "${CHUNK_DIR}" \
    --outdir "${SPLIT_DIR}" \
    ${CONFIG_FLAG}
SBATCH
)

echo "Submitted SLURM array job: $JOB_ID"
echo "Monitor with:  squeue -j $JOB_ID"
echo "Logs:          $LOG_DIR/split_*.out"
echo ""
echo "Once complete, run phase 3:"
echo "  ./3_submit_merge.sh $OUTDIR"
