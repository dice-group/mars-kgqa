#!/bin/bash

## Sample usage:
## bash execute_experiment.sh --gpu 0 --approach PBSG_MHOP \
#   --dataset QALD10_UPDATED_TENTRISQ10 --split TEST --llm GPTOSS120B \
#   --topn-count 20 --mhop-limit 5 --include-pattern-count \
#   --use-aug-similarity --language en --conc-ex-limit 2 --use-class-info

set -euo pipefail

# Determine the directory of the current script
CUR_SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # This will get overriden at our next source call

# Loading environment variables (also loads slurm specific config if needed)
source "$CUR_SCRIPT_DIR/setup/env.sh"

export ENV_PRELOADED=true

# Assign system name
export RUN_SYS_NAME="${CLUSTER_NAME:-$(hostname)}"

# Helper: print usage
usage() {
  cat <<EOF
Usage: $0 [OPTIONS] --approach <APPROACH> --dataset <DATASET> \\
          --split <SPLIT> --llm <LLM> [--use-gold] [other flags]

Options:
  --gpu <ID|all>                GPU device to expose to llama‑swap (default: all)
  --port <PORT>                 Host port for llama‑swap (default: random 9200‑9300)
  --debug                       Run run.py under debugpy (adds remote‑debug support)
  --use-gold                    Use gold entity and relation annotations if provided
  --filter-entities             Filter out entities that do not meet certain criteria
  --topn-count <N>              Maximum number of top‑N candidates to keep per step
  --mhop-limit <N>              Maximum number of hops allowed in multi‑hop reasoning
  --include-pattern-count       Include the count of matched patterns in the output
  --refine-sparql               Run a post‑processing step to refine generated SPARQL
  --entity-annotator <NAME>     Entity annotator to apply (e.g. AUG_EL)
  --use-aug-similarity          Use augmented sequence for similarity computations
  --language <CODE>             Language code for the questions (default: en)
  --conc-ex-limit <N>           Number of concrete examples to use for each pattern (default: 0)
  --use-class-info              Use class (domain/range) information in verbalizations
  --verify-update-sparql        Use the results from the generated SPARQL to verify if it returns a seemingly expected answer. Update the SPARQL one last time if it does not.
  -h, --help                    Show this help message
EOF
  exit 1
}


# Default values for core options
GPU_DEVICE="all"
PORT=""
MODE="run"   # normal execution; can be changed to "debug" via --debug
USE_GOLD="false"

# Default values for the optional flags – empty means "not passed"
FILTER_ENTITIES="false"
TOPN_COUNT=""          # optional, only added if user supplies a value
MHOP_LIMIT=""         # optional, only added if user supplies a value
INCLUDE_PATTERN_COUNT="false"
REFINE_SPARQL="false"
ENTITY_ANNOTATOR=""   # optional, only added if user supplies a value
USE_AUG_SIMILARITY="false"
LANGUAGE="en"
CONC_EX_LIMIT=""      # optional, only added if user supplies a value
USE_CLASS_INFO="false"
VERIFY_UPDATE_SPARQL="false"


# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpu)           GPU_DEVICE="${2:?Missing value for --gpu}"; shift 2 ;;
    --port)          PORT="${2:?Missing value for --port}"; shift 2 ;;
    --debug)         MODE="debug"; shift ;;
    --use-gold)      USE_GOLD="true"; shift ;;
    --filter-entities) FILTER_ENTITIES="true"; shift ;;
    --topn-count)    TOPN_COUNT="${2:?Missing value for --topn-count}"; shift 2 ;;
    --mhop-limit)    MHOP_LIMIT="${2:?Missing value for --mhop-limit}"; shift 2 ;;
    --include-pattern-count) INCLUDE_PATTERN_COUNT="true"; shift ;;
    --refine-sparql) REFINE_SPARQL="true"; shift ;;
    --entity-annotator) ENTITY_ANNOTATOR="${2:?Missing value for --entity-annotator}"; shift 2 ;;
    --approach)      APPROACH="${2:?Missing value for --approach}"; shift 2 ;;
    --dataset)       DATASET="${2:?Missing value for --dataset}"; shift 2 ;;
    --split)         SPLIT="${2:?Missing value for --split}"; shift 2 ;;
    --llm)           LLM="${2:?Missing value for --llm}"; shift 2 ;;
    --use-aug-similarity)   USE_AUG_SIMILARITY="true"; shift ;;
    --language)             LANGUAGE="${2:?Missing value for --language}"; shift 2 ;;
    --conc-ex-limit) CONC_EX_LIMIT="${2:?Missing value for --conc-ex-limit}"; shift 2 ;;
    --use-class-info)       USE_CLASS_INFO="true"; shift ;;
    --verify-update-sparql) VERIFY_UPDATE_SPARQL="true"; shift ;;
    -h|--help)       usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

# Adjust GPU value for llama-swap's Docker container
if [[ "$GPU_DEVICE" != "all" && "$GPU_DEVICE" != \"device=*\" ]]; then
  GPU_DEVICE="\"device=${GPU_DEVICE}\""
fi

# Validate required args
[[ -z "${APPROACH:-}" ]] && { echo "Error: --approach is required"; usage; }
[[ -z "${DATASET:-}"  ]] && { echo "Error: --dataset is required";  usage; }
[[ -z "${SPLIT:-}"    ]] && { echo "Error: --split is required";    usage; }
[[ -z "${LLM:-}"      ]] && { echo "Error: --llm is required";      usage; }

# Choose a free port if none supplied
if [[ -z "$PORT" ]]; then
  for i in {1..10}; do
    PORT=$(shuf -i 10000-11000 -n 1)
    if ! ss -ltnp | grep -q ":$PORT "; then
      break
    fi
    PORT=""
  done
  : ${PORT:?"Failed to find a free port in 10000-11000"}
fi

export GPU_DEVICE

# Start llama‑swap container (and ensure it stops on script exit)
bash setup/llama_swap_control.sh start "$PORT"

# Register a trap to stop the container when the script exits or is interrupted
cleanup() {
  echo "Cleaning up processes..."
  # Prevent the trap from firing again (e.g., when EXIT follows INT)
  trap - EXIT INT TERM
  bash setup/llama_swap_control.sh stop "$PORT" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait for llama‑swap to become reachable
echo "Waiting for llama‑swap to become reachable..."
up=0
for i in {1..60}; do
  if curl -s "http://127.0.0.1:$PORT/v1/models" > /dev/null 2>&1; then
    echo "Llama‑swap is up."
    up=1
    break
  fi
  sleep 1
done

# If the loop finished without a successful curl, exit with an error
if [[ $up -ne 1 ]]; then
  echo "Error: Llama‑swap did not start." >&2
  exit 1
fi

export LLAMA_SWAP_OPENAI_ENDPOINT="http://127.0.0.1:${PORT}/v1"
export OWUI=""

# Build the argument list for run.py
RUN_ARGS=(
  --approach   "$APPROACH"
  --dataset    "$DATASET"
  --split      "$SPLIT"
  --llm        "$LLM"
)

[[ "$USE_GOLD" == "true" ]]            && RUN_ARGS+=(--use-gold)
[[ "$FILTER_ENTITIES" == "true" ]]     && RUN_ARGS+=(--filter-entities)
[[ -n "$TOPN_COUNT" ]]                 && RUN_ARGS+=(--topn-count "$TOPN_COUNT")
[[ -n "$MHOP_LIMIT" ]]                 && RUN_ARGS+=(--mhop-limit "$MHOP_LIMIT")
[[ "$INCLUDE_PATTERN_COUNT" == "true" ]] && RUN_ARGS+=(--include-pattern-count)
[[ "$REFINE_SPARQL" == "true" ]]       && RUN_ARGS+=(--refine-sparql)
[[ -n "$ENTITY_ANNOTATOR" ]]           && RUN_ARGS+=(--entity-annotator "$ENTITY_ANNOTATOR")
[[ "$USE_AUG_SIMILARITY" == "true" ]]  && RUN_ARGS+=(--use-aug-similarity)
[[ -n "$LANGUAGE" ]]                   && RUN_ARGS+=(--language "$LANGUAGE")
[[ -n "$CONC_EX_LIMIT" ]]              && RUN_ARGS+=(--conc-ex-limit "$CONC_EX_LIMIT")
[[ "$USE_CLASS_INFO" == "true" ]]      && RUN_ARGS+=(--use-class-info)
[[ "$VERIFY_UPDATE_SPARQL" == "true" ]] && RUN_ARGS+=(--verify-update-sparql)

# Launch experiment via pylauncher.sh
echo "Launching experiment via pylauncher.sh ($MODE)..."
bash pylauncher.sh "$MODE" src.run "${RUN_ARGS[@]}"

# End of script – the trap will stop the container automatically