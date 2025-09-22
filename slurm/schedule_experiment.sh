#!/bin/bash

# Sample usage: bash slurm/schedule_experiment.sh --approach PBSG_MHOP --dataset QALD10_UPDATED_TENTRISQ10 --split TEST --llm GPTOSS120B --topn-count 20 --mhop-limit 5 --include-pattern-count

PASSED_ARGS="$@"

CUR_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

USE_GOLD="pred_ent"
# Iterate over all passed flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --approach)   APPROACH="$2"; shift 2 ;;
    --dataset)    DATASET="$2";  shift 2 ;;
    --split)      SPLIT="$2";    shift 2 ;;
    --llm)        LLM="$2";      shift 2 ;;
    --use-gold)   USE_GOLD="gold_ent";      shift 2 ;;
    *)            shift ;;  # ignore other args
  esac
done

CLUSTER_LOG_DIR=$CUR_SCRIPT_DIR/../cluster_logs

mkdir $CLUSTER_LOG_DIR

# Construct a readable run name
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_NAME="${APPROACH}-${DATASET}-${SPLIT}-${LLM}-${USE_GOLD}-${TIMESTAMP}"

sbatch --job-name=$RUN_NAME --gres=gpu:h100:1 --time=10:00:00 -o "$CLUSTER_LOG_DIR/%x__slurm-%j.out" $CUR_SCRIPT_DIR/../execute_experiment.sh $PASSED_ARGS