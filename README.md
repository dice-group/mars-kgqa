## MARS: Multi-hop Context Augmented Retrieval-based SPARQL Generation for Multilingual Question Answering over Knowledge Graphs

A semantic-parsing based (Wikidata) KGQA system that generates SPARQL for a given natural language query.

### Local Setup

#### Prerequisites
Make sure you have Docker (https://docs.docker.com/) and Python (>=3.12.3) installed.

#### Dependencies Installation
To install the dependencies, run:
```bash
bash setup/setup_venv.sh
```

This creates a python virtual environment, which will be used for the experiments.

#### LLM Management

MARS uses a *llama-swap* (https://github.com/mostlygeek/llama-swap) based *llama.cpp* (https://github.com/ggml-org/llama.cpp) server deployment for its LLMs. It expects model weights to be available at the path provided in the `$LLAMA_CACHE` environment variable. You can either download these weights using the *llama-swap* instance by first running it:
```bash
GPU_DEVICE='"device=0"' bash setup/llama_swap_control.sh start 9292
```
and then downloading the required models using the *llama-swap* ui: http://localhost:9292/ui/models or you can manually download the models to this directory using the `llama-cli` tool: https://github.com/ggml-org/llama.cpp?tab=readme-ov-file#obtaining-and-quantizing-models.

### Running Experiments

Here's a sample command to run MARS pipeline for QALD10 dataset:
```bash
bash execute_experiment.sh --gpu 0 --approach PBSG_MHOP \
    --dataset QALD10_UPDATED_TENTRISQ10 --split TEST --llm GPTOSS120B \
    --topn-count 20 --mhop-limit 5 --include-pattern-count \
    --use-aug-similarity --language en --conc-ex-limit 2 --use-class-info
```

**Note**: At the moment, MARS used pre-annotated data in QALD format (e.g., [tentrisq10_aug_gold.json](data_dir/processed_kgqa_ds/qald10/test/tentrisq10_aug_gold.json)). We will integrate on-the-fly annotating logic soon.

For SLURM-based setup, look into the scripts provided in: [slurm/](slurm/).

<!-- TODO: Write more details here-->

<!-- TODO: Add link to Zenodo resources-->