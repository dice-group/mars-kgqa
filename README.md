# MARS: Multi-hop Retrieval-Augmented SPARQL Generation for Multilingual KGQA

A semantic-parsing based KGQA system that generates ([Wikidata](https://www.wikidata.org/)) SPARQL for a given natural language query.


<figure style="display:block; margin:2rem auto; text-align:center;">
  <img src="data_dir/figures/mars-kgqa-overview.png"
       alt="MARS pipeline overview"
       width="800"
       style="max-width:100%; height:auto; display:block; margin:0 auto;">
  <figcaption style="margin-top:0.4rem; font-size:0.9rem; color:#666;">
    An overview of our MARS pipeline on an example question:
    <i>"When was the creator of Saturday Night Live born?"</i> (from the <a href="https://github.com/KGQA/QALD-10">QALD‑10</a> dataset).
  </figcaption>
</figure>

## Abstract
In multilingual real‑world scenarios, large language models (LLMs) are being increasingly applied in knowledge-intensive tasks where access to up-to-date and grounded knowledge is typically essential. However, LLMs hallucinate facts and fine-tuning them remains computationally inefficient and resource-intensive. By synthesizing knowledge graphs (KGs) and LLMs, systems can benefit from (a) explicit symbolic knowledge that allows continuous efficient updates, and (b) rapidly evolving LLM reasoning abilities, which together might have the potential to strengthen both accuracy and robustness of system results. We propose MARS, a scalable retrieval and reasoning system for multilingual knowledge graph question answering (KGQA) without requiring costly model fine-tuning. MARS links question entities to a KG and iteratively retrieves relevant next-hop information from the graph, feeding this structured information context-augmented into the LLM. In multiple rounds, the LLM uses this information to refine its understanding of the question-relevant context and generates a SPARQL query. We evaluate our approach on three established KGQA benchmarks with several LLMs and settings, providing insights with our ablation studies and error analysis. Our approach achieves robust state-of-the-art results, surpassing five baseline systems.

## Local Setup

### Prerequisites
Make sure you have Docker (<https://docs.docker.com/>) and Python (>=3.12.3) installed.

### Dependencies Installation
To install the dependencies, run:
```bash
bash setup/setup_venv.sh
```

This creates a python virtual environment, which will be used for the experiments.

### Wikidata Relations Indexing
We pre‑index the URIs and labels of Wikidata relations for quicker access. To run the process, simply execute the script below:
```bash
python -m src.cache.wikidata_relation_info_extractor
```

### LLM Management
MARS utilizes local LLM instances served via a [*llama.cpp*](https://github.com/ggml-org/llama.cpp) server, managed through [`setup/llama_server_control.sh`](setup/llama_server_control.sh).

The server expects the model weights to be located in the directory referenced by the `$LLAMA_CACHE` environment variable. Make sure this variable points to a valid directory **before** you start downloading any models.

#### Recommended download method

1. Install the `llama-cli` tool (instructions are in the [llama.cpp README](https://github.com/ggml-org/llama.cpp?tab=readme-ov-file#llama-cli)).
2. Use `llama-cli` to fetch the models you need, for example:

```bash
llama-cli -hf nomic-ai/nomic-embed-text-v2-moe-GGUF:F16
llama-cli -hf unsloth/gpt-oss-120b-GGUF:Q8_0
```

#### Starting the server

```bash
bash setup/llama_server_control.sh start
```

By default the server starts on port `9292`. To use a different port:

```bash
bash setup/llama_server_control.sh start 9393
```

Other useful commands:

```bash
bash setup/llama_server_control.sh stop 9292
bash setup/llama_server_control.sh restart 9292
```

#### Which models are required?

The complete list of configured models is defined in [`setup/llama_server_models.ini`](setup/llama_server_models.ini). You don't have to download every entry, only the models you plan to use.

## Running Experiments

> **Note**: Entity annotations in the QALD-formatted dataset files (e.g., [tentrisq10_aug_gold.json](data_dir/processed_kgqa_ds/qald10/test/tentrisq10_aug_gold.json)) are generated using the [GRASP entity linking pipeline](https://github.com/dice-group/grasp_el). See the [annotation pipeline documentation](https://github.com/dice-group/grasp_el/blob/main/ANNOTATION_PIPELINE.md) for details on how to annotate questions with entity and property links.

Here's a sample command to run MARS pipeline for QALD10 dataset:
```bash
bash execute_experiment.sh --gpu 0 --approach PBSG_MHOP \
    --dataset QALD10_UPDATED_TENTRISQ10 --split TEST --llm GPTOSS120B \
    --topn-count 20 --mhop-limit 5 --include-pattern-count \
    --use-aug-similarity --language en --conc-ex-limit 2 --use-class-info
```

For SLURM-based setup, look into the scripts provided in: [`slurm/`](slurm/).

## Resources

> **Note:** Future updates to supplementary materials will be maintained in the [`supplementary_material/`](supplementary_material/) directory. See the markdown files there for the latest resources.

### Error Analysis Pipeline
Our automated error analysis pipeline is already integrated in our experiments. Some examples of the final compiled analysis can be found at: [`data_dir/analysis/`](data_dir/analysis/).