#!/bin/bash
#============================================================================
# 3_submit_merge.sh — Phase 3: Merge partial split files into final outputs.
#
# Usage:
#   ./3_submit_merge.sh <output_dir>
#
# Example:
#   ./3_submit_merge.sh /scratch/wd_split
#
# Expects partial files from phase 2 in <output_dir>/split_out/
# Writes final output to <output_dir>/main.nt.zst and <output_dir>/scholarly.nt.zst
#============================================================================
set -euo pipefail

OUTDIR="${1:?Usage: $0 <output_dir>}"

SPLIT_DIR="${OUTDIR}/split_out"
LOG_DIR="${OUTDIR}/logs"

mkdir -p "$LOG_DIR"

# Verify partial files exist
MAIN_COUNT=$(ls "${SPLIT_DIR}"/main_*.nt.zst 2>/dev/null | wc -l)
SCH_COUNT=$(ls "${SPLIT_DIR}"/scholarly_*.nt.zst 2>/dev/null | wc -l)

if [ "$MAIN_COUNT" -eq 0 ] || [ "$SCH_COUNT" -eq 0 ]; then
    echo "ERROR: No partial files found in $SPLIT_DIR"
    echo "       Run phase 2 first: ./2_submit_split.sh $OUTDIR"
    exit 1
fi

echo "Phase 3: Merge"
echo "  Split dir:     $SPLIT_DIR"
echo "  Main parts:    $MAIN_COUNT"
echo "  Scholarly parts: $SCH_COUNT"
echo "  Output:        $OUTDIR/main.nt.zst"
echo "                 $OUTDIR/scholarly.nt.zst"
echo ""

JOB_ID=$(sbatch --parsable <<SBATCH
#!/bin/bash
#SBATCH --job-name=wd-merge
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=06:00:00
#SBATCH --output=${LOG_DIR}/merge.out
#SBATCH --error=${LOG_DIR}/merge.err

set -euo pipefail

echo "Merge started: \$(date)"

# Compute total compressed sizes for progress tracking
MAIN_TOTAL_BYTES=\$(ls -l "${SPLIT_DIR}"/main_*.nt.zst | awk '{s+=\$5} END {print s}')
SCH_TOTAL_BYTES=\$(ls -l "${SPLIT_DIR}"/scholarly_*.nt.zst | awk '{s+=\$5} END {print s}')

merge_with_progress() {
    local label="\$1"
    local pattern="\$2"
    local output="\$3"
    local total_bytes="\$4"
    local count="\$5"

    echo ""
    echo "Merging \${label} (\${count} parts, \$(numfmt --to=iec \${total_bytes}) compressed)..."

    if command -v pv &>/dev/null; then
        # pv tracks bytes flowing through the pipe
        ls -1 \${pattern} | sort | while read f; do
            zstd -d --stdout --no-progress "\$f"
        done | pv -N "\${label}" -pterba | zstd -T0 -3 --no-progress -o "\${output}"
    else
        # Fallback: log progress by file count
        local i=0
        ls -1 \${pattern} | sort | while read f; do
            i=\$((i + 1))
            echo -ne "  [\${i}/\${count}] \$(basename \$f)\\r" >&2
            zstd -d --stdout --no-progress "\$f"
        done | zstd -T0 -3 --no-progress -o "\${output}"
        echo "" >&2
    fi
}

merge_with_progress "main"      "${SPLIT_DIR}/main_*.nt.zst"      "${OUTDIR}/main.nt.zst"      "\$MAIN_TOTAL_BYTES" "$MAIN_COUNT"
merge_with_progress "scholarly"  "${SPLIT_DIR}/scholarly_*.nt.zst" "${OUTDIR}/scholarly.nt.zst"  "\$SCH_TOTAL_BYTES"  "$SCH_COUNT"

echo ""
echo "=== Final Output ==="
ls -lh "${OUTDIR}/main.nt.zst" "${OUTDIR}/scholarly.nt.zst"

echo ""
echo "To decompress to plain N-Triples:"
echo "  zstd -d ${OUTDIR}/main.nt.zst"
echo "  zstd -d ${OUTDIR}/scholarly.nt.zst"

echo ""
echo "Merge finished: \$(date)"
SBATCH
)

echo "Submitted SLURM merge job: $JOB_ID"
echo "Monitor with:  squeue -j $JOB_ID"
echo "Log:           $LOG_DIR/merge.out"
