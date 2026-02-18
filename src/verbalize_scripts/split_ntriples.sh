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

# Output directory (can be the same as input directory or another location)
OUTPUT_DIR="${FILE_DIR}/${K_VAL}_chunks"

echo "=== split_ntriples.sh started ==="
echo "Chunk size (lines per file):  $K_VAL"
echo "Input file:                 $INPUT_PATH"
echo "Output directory:           $OUTPUT_DIR"

mkdir -p $OUTPUT_DIR
echo "Created output directory (if it didn't exist)."

# Split the file into numbered chunks with the .nt suffix, placing them in $OUTPUT_DIR
echo "Running split command..."
split -d -n "${K_VAL}" --additional-suffix=.nt "${INPUT_PATH}" "${OUTPUT_DIR}/dataset_chunk_"
echo "Split complete. Chunks are stored in $OUTPUT_DIR."

echo "=== split_ntriples.sh finished ==="