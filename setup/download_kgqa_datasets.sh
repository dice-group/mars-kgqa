#!/bin/bash
set -eu

# Determine the directory of the current script
CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source $CUR_SCRIPT_DIR/env.sh

#echo "Current script directory: "$CUR_SCRIPT_DIR

KGQA_DATA_PATH=$PROJ_DATA_DIR"/kgqa_datasets"

#echo "KGQA dataset directory: "$PROJ_DATA_DIR

mkdir -p $KGQA_DATA_PATH

cd $KGQA_DATA_PATH

# QALD10: https://github.com/KGQA/QALD-10
wget https://raw.githubusercontent.com/KGQA/QALD_10/main/data/qald_10/qald_10.json -P qald10/
wget https://raw.githubusercontent.com/KGQA/QALD-10/main/data/qald_9_plus/qald_9_plus_train_wikidata.json -P qald10/