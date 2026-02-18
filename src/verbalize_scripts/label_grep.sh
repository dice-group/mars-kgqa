#!/bin/bash

# Sample usage: sbatch -N 1 -n 1 -c 4 -t 05:00:00 --partition normal --mem 200G src/verbalize_scripts/label_grep.sh
# Last run 16.02.2026: 0:43:18

set -eu

# Determine the project root (two levels up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(realpath "$SCRIPT_DIR/../..")"
DATA_DIR="$PROJECT_ROOT/data_dir/verbalization"

mkdir -p $DATA_DIR

echo "Copying file to RAM.."

cp /scratch/hpc-prf-merlin/project_data/wikidata_qald10_dumpwikidata.gz /dev/shm/

echo "Copy complete, starting extraction.."

zcat /dev/shm/wikidata.gz | grep -F "<http://www.w3.org/2000/01/rdf-schema#label>" > "$DATA_DIR/rdf_labels.nt"

echo "Extraction finished."