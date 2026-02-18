#!/bin/bash

# Sample usage: sbatch -N 1 -n 1 -c 4 -t 01:00:00 -o data_dir/verbalization/logs/%j_split_ntriples.log --partition normal --mem 200G src/verbalize_scripts/split_ntriples.sh
# Last run 18.02.2026: 0:16:33

set -eu

# Number of lines per chunk (adjust as needed)
K_VAL=2000

# Directory that holds the input file
FILE_DIR=/scratch/hpc-prf-merlin/project_data/wikidata_qald10_dump

# Input file name (must exist in $FILE_DIR)
FILE_NAME=wikidata.nt

# Full path to the input file
INPUT_PATH="${FILE_DIR}/${FILE_NAME}"
OUTPUT_DIR="${FILE_DIR}/${K_VAL}_chunks"

echo "=== split_ntriples.sh started ==="
echo "Requested # of chunks:       $K_VAL"
echo "Input file:                 $INPUT_PATH"
echo "Output directory:           $OUTPUT_DIR"

mkdir -p "$OUTPUT_DIR"
echo "Created output directory (if it didn't exist)."

# Count total lines in the source file
TOTAL_LINES=$(wc -l < "$INPUT_PATH")
echo "Total lines in input file: $TOTAL_LINES"

# Compute lines‑per‑chunk (ceil division)
#   ceil(a/b) = (a + b - 1) / b   (integer arithmetic)
LINES_PER_CHUNK=$(( (TOTAL_LINES + K_VAL - 1) / K_VAL ))
echo "Lines per chunk (rounded up): $LINES_PER_CHUNK"

# Split the file by the computed line count
echo "Running split command..."
split -d -a 4 -l "$LINES_PER_CHUNK" --additional-suffix=.nt "$INPUT_PATH" "${OUTPUT_DIR}/dataset_chunk_"
echo "Split complete. Chunks are stored in $OUTPUT_DIR."

echo "=== split_ntriples.sh finished ==="