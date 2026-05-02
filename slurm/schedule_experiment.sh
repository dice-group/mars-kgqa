#!/bin/bash

# Sample usage: bash slurm/schedule_experiment.sh --approach PBSG_MHOP \
#   --dataset QALD10_UPDATED_TENTRISQ10 --split TEST --llm GPTOSS120B \
#   --topn-count 20 --mhop-limit 5 --include-pattern-count \
#   --use-aug-similarity --language en --conc-ex-limit 2 --use-class-info
set -eu

PASSED_ARGS="$@"
CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

USE_GOLD="pred_ent"          # default value for run name to indicate that the predicted entites are to be used
USE_AUG_SIMILARITY="false"
USE_CLASS_INFO="false"
VERIFY_UPDATE_SPARQL="false"
LANGUAGE="en"

# Iterate over all passed flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --approach)          APPROACH="$2"; shift 2 ;;
    --dataset)           DATASET="$2";  shift 2 ;;
    --split)             SPLIT="$2";    shift 2 ;;
    --llm)               LLM="$2";      shift 2 ;;
    --use-gold)          USE_GOLD="gold_ent"; shift 1 ;;
    --topn-count)        TOPN_COUNT="$2"; shift 2 ;;
    --mhop-limit)        MHOP_LIMIT="$2"; shift 2 ;;
    --include-pattern-count)  INCLUDE_PATTERN_COUNT=1; shift 1 ;;
    --use-aug-similarity)    USE_AUG_SIMILARITY="true"; shift 1 ;;
    --language)          LANGUAGE="${2:?Missing value for --language}"; shift 2 ;;
    --conc-ex-limit)     CONC_EX_LIMIT="$2"; shift 2 ;;
    --use-class-info)    USE_CLASS_INFO="true"; shift 1 ;;
    --verify-update-sparql) VERIFY_UPDATE_SPARQL="true"; shift 1 ;;
    *)                    shift ;;   # ignore unknown args
  esac
done

CLUSTER_LOG_DIR=$CUR_SCRIPT_DIR/../data_dir/cluster_logs
mkdir -p "$CLUSTER_LOG_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_NAME="${LANGUAGE}-${APPROACH}-${DATASET}-${SPLIT}-${LLM}-${USE_GOLD}"
[[ "$USE_AUG_SIMILARITY" == "true" ]] && RUN_NAME="${RUN_NAME}-augsim"
[[ "$USE_CLASS_INFO" == "true" ]] && RUN_NAME="${RUN_NAME}-clsinf"
[[ "$VERIFY_UPDATE_SPARQL" == "true" ]] && RUN_NAME="${RUN_NAME}-verupdt"
[[ -n "${CONC_EX_LIMIT:-}" ]] && RUN_NAME="${RUN_NAME}-concelim${CONC_EX_LIMIT}"
RUN_NAME="${RUN_NAME}-${TIMESTAMP}"

sbatch --job-name="$RUN_NAME" --mem=250G --cpus-per-task=16 --gres=gpu:h100:1 --time=30:00:00 \
       -o "$CLUSTER_LOG_DIR/slurm-%j__%x.out" \
       "$CUR_SCRIPT_DIR/../execute_experiment.sh" $PASSED_ARGS