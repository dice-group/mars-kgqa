#!/bin/bash
#============================================================================
# 1_submit_presplit.sh — Phase 1: Submit the pre-split as a SLURM job.
#
# Usage:
#   ./1_submit_presplit.sh <input.nt.gz> <output_dir> [num_chunks]
#
# Example:
#   ./1_submit_presplit.sh /data/wikidata/latest-all.nt.gz /scratch/wd_split 200
#============================================================================
set -euo pipefail

CUR_SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # This will get overriden at our next source call

# Loading environment variables (also loads slurm specific config if needed)
source "$CUR_SCRIPT_DIR/../setup/env.sh"

# Environment must be loaded in the calling script
source $PROJ_VENV_DIR/bin/activate

INPUT="${1:?Usage: $0 <input.nt.gz> <output_dir> [num_chunks]}"
OUTDIR="${2:?Usage: $0 <input.nt.gz> <output_dir> [num_chunks]}"
NUM_CHUNKS="${3:-200}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHUNK_DIR="${OUTDIR}/chunks"
LOG_DIR="${OUTDIR}/logs"

mkdir -p "$CHUNK_DIR" "$LOG_DIR"

echo "Phase 1: Pre-split"
echo "  Input:    $INPUT"
echo "  Chunks:   $NUM_CHUNKS"
echo "  Chunk dir: $CHUNK_DIR"
echo ""

JOB_ID=$(sbatch --parsable <<SBATCH
#!/bin/bash
#SBATCH --job-name=wd-presplit
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=40:00:00
#SBATCH --output=${LOG_DIR}/presplit.out
#SBATCH --error=${LOG_DIR}/presplit.err

set -euo pipefail

pip install --quiet tqdm 2>/dev/null || true

echo "Starting pre-split: \$(date)"
python3 "${SCRIPT_DIR}/wikidata_presplit.py" \
    "${INPUT}" \
    --chunks ${NUM_CHUNKS} \
    --outdir "${CHUNK_DIR}"

echo "Pre-split finished: \$(date)"
echo "Chunks produced: \$(ls ${CHUNK_DIR}/chunk_*.nt.zst 2>/dev/null | wc -l)"
SBATCH
)

echo "Submitted SLURM job: $JOB_ID"
echo "Monitor with:  squeue -j $JOB_ID"
echo "Log:           $LOG_DIR/presplit.out"
echo ""
echo "Once complete, run phase 2:"
echo "  ./2_submit_split.sh $OUTDIR"
