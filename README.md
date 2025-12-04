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
<!-- MARS relies on local LLM instances, for which it uses a *llama-swap*-based (https://github.com/mostlygeek/llama-swap) *llama.cpp* (https://github.com/ggml-org/llama.cpp) server deployment. It expects model weights to be available at the path provided in the `$LLAMA_CACHE` environment variable, please make sure that this value points to an existing directory before you download the models. The recommended way to download the models is by having  `llama-cli` tool installed locally (https://github.com/ggml-org/llama.cpp?tab=readme-ov-file#llama-cli). Once installed, you can simply download the chosen model using the following commands:
```bash
llama-cli -hf nomic-ai/nomic-embed-text-v2-moe-GGUF:F16
llama-cli -hf unsloth/gpt-oss-120b-GGUF:Q8_0
```

You can also download these the models using the *llama-swap* instance by first running it:
```bash
GPU_DEVICE='"device=0"' bash setup/llama_swap_control.sh start 9292
```
and then downloading the required models using the *llama-swap* ui: http://localhost:9292/ui/models, however, this can lead to request timeout issues for larger models or lower internet bandwidths.

To find the full list of models used in our implementation, please look into [llama_swap_config.yml](setup/llama_swap_config.yml). You do not need to download all of the mentioned models, just downloading the ones you need is sufficient. -->
MARS utilizes local LLM instances that are served via a *llama‑swap*‑based deployment of *llama.cpp* (see the repositories [`mostlygeek/llama-swap`](https://github.com/mostlygeek/llama-swap) and [`ggml‑org/llama.cpp`](https://github.com/ggml-org/llama.cpp)).  

The server expects the model weights to be located in the directory referenced by the `$LLAMA_CACHE` environment variable. Make sure this variable points to a valid directory **before** you start downloading any models.

#### Recommended download method

1. Install the `llama-cli` tool (instructions are in the [llama.cpp README](https://github.com/ggml-org/llama.cpp?tab=readme-ov-file#llama-cli)).  
2. Use `llama-cli` to fetch the models you need, for example:

```bash
llama-cli -hf nomic-ai/nomic-embed-text-v2-moe-GGUF:F16
llama-cli -hf unsloth/gpt-oss-120b-GGUF:Q8_0
```

#### Alternative: downloading through a running *llama‑swap* instance

```bash
GPU_DEVICE='"device=0"' bash setup/llama_swap_control.sh start 9292
```

After the service is up, open the UI at <http://localhost:9292/ui/models> and download the desired models there.  
> **Note:** This method may suffer from request‑timeout problems with large models or on slow internet connections.

#### Which models are required?

The complete list of models used by MARS is defined in [`setup/llama_swap_config.yml`](setup/llama_swap_config.yml). You don't have to download every entry, only the models you plan to use.

## Running Experiments

Here's a sample command to run MARS pipeline for QALD10 dataset:
```bash
bash execute_experiment.sh --gpu 0 --approach PBSG_MHOP \
    --dataset QALD10_UPDATED_TENTRISQ10 --split TEST --llm GPTOSS120B \
    --topn-count 20 --mhop-limit 5 --include-pattern-count \
    --use-aug-similarity --language en --conc-ex-limit 2 --use-class-info
```

> **Note**: At the moment, MARS uses pre-annotated data in QALD format (e.g., [tentrisq10_aug_gold.json](data_dir/processed_kgqa_ds/qald10/test/tentrisq10_aug_gold.json)). We will integrate end-to-end entity/relations annotating logic soon.

For SLURM-based setup, look into the scripts provided in: [`slurm/`](slurm/).

## Resources

### Error Analysis Pipeline
Our automated error analysis pipeline is already integrated in our experiments. Some examples of the final compiled analysis can be found at: [`data_dir/analysis/`](data_dir/analysis/).

### Gerbil Results
Links to all the gerbil results from our experiments can be found at:  [`data_dir/gerbil_results/`](data_dir/gerbil_results/).