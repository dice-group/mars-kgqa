# Appendix

## Models Tested with MARS

We tested MARS with the following models:

| Model | HuggingFace Repo |
|-------|------------------|
| Gemma 3 | [unsloth/gemma-3-27b-it-GGUF](https://hf.co/unsloth/gemma-3-27b-it-GGUF) |
| Qwen3 | [unsloth/Qwen3-32B-GGUF](https://hf.co/unsloth/Qwen3-32B-GGUF) |
| Qwen3.6-27B | [unsloth/Qwen3.6-27B-GGUF](https://hf.co/unsloth/Qwen3.6-27B-GGUF) |
| Qwen3-Coder | [unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF](https://hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF) |
| Mistral-Small-3.2 | [unsloth/Mistral-Small-3.2-24B-Instruct-2506-GGUF](https://hf.co/unsloth/Mistral-Small-3.2-24B-Instruct-2506-GGUF) |
| Magistral-Small | [unsloth/Magistral-Small-2509-GGUF](https://hf.co/unsloth/Magistral-Small-2509-GGUF) |
| gpt-oss-120b | [unsloth/gpt-oss-120b-GGUF](https://hf.co/unsloth/gpt-oss-120b-GGUF) |
| GLM-4.5-Air | [unsloth/GLM-4.5-Air-GGUF](https://hf.co/unsloth/GLM-4.5-Air-GGUF) |
| DeepSeek-R1 Distill-Qwen3 | [unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF](https://hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF) |
| Llama-Nemotron-Super | [unsloth/Llama-3_3-Nemotron-Super-49B-v1_5-GGUF](https://hf.co/unsloth/Llama-3_3-Nemotron-Super-49B-v1_5-GGUF) |
| Nemotron-3-Super-120B-A12B | [unsloth/NVIDIA-Nemotron-3-Super-120B-A12B-GGUF](https://hf.co/unsloth/NVIDIA-Nemotron-3-Super-120B-A12B-GGUF) |
| Llama-4-Scout | [unsloth/Llama-4-Scout-17B-16E-Instruct-GGUF](https://hf.co/unsloth/Llama-4-Scout-17B-16E-Instruct-GGUF) |
| Gemma-4-31B | [unsloth/gemma-4-31B-it-GGUF](https://hf.co/unsloth/gemma-4-31B-it-GGUF) |

## Performance Tables

- [Full MARS performance tables (in CSV)*](https://files.dice-research.org/projects/MARS/EKAW/run_log/best_1/processed_kgqa_ds/)
- [Full baseline performance tables (in CSV)*](https://files.dice-research.org/projects/MARS/EKAW/baseline_data)
- [Ablation result tables (Already in markdown)](https://files.dice-research.org/projects/MARS/EKAW/analyses/ablation/)

\* To find the CSV tables, you will have to navigate to a directory like this: [qald10/test/prediction/tentrismain_aug_gold/gerbil/en__noctua2__PBSG_MHOP__t20-h10-pc-ausm-grasp-el-exlim10-clsinf-verupdt__gptoss120b.csv/](https://files.dice-research.org/projects/MARS/EKAW/run_log/best_1/processed_kgqa_ds/qald10/test/prediction/tentrismain_aug_gold/gerbil/en__noctua2__PBSG_MHOP__t20-h10-pc-ausm-grasp-el-exlim10-clsinf-verupdt__gptoss120b.csv/)

## MARS Performance Analyses

- [MARS QALD10 performance](../data_dir/analysis/qald10_test_pbsg_comparison.md)
- [MARS QALD9Plus performance](../data_dir/analysis/qald9plus_test_pbsg_comparison.md)
- [MARS scaling across MHOP and TOPN](../data_dir/analysis/mhop_scaling.md)

## Dataset Analyses

- [Multi-Hop Distribution](../data_dir/analysis/multi-hop_distribution.md)
- [Language Distribution](../data_dir/analysis/language_distribution.md)

## SPARQLReasoner Prompt

Prompt for graph traversal and SPARQL query generation:

```text
Given a natural language question, identified entities and a set of Wikidata triple patterns (subject, predicate, object) including entity IDs and domain/range type restrictions, tell if you need to look further into the paths to generate a Wikidata SPARQL for the question. If yes, list the index based on the 0-indexing, of the patterns. If not, then generate a valid wikidata SPARQL query utilizing the relevant provided IDs that answers the question. Prioritize triple patterns where the entity IDs appear relevant to the question and the domain/range types align with the expected answer type. Discard any triple patterns that do not contribute to answering the question. Do not try to retrieve labels unless explicitly asked. 

Strictly follow ONLY one of the provided "Answer Format" depending upon your response, do not write anything else. 

Question: {question} 

### Identified Question Entities: 
{entities} 

### Triple Patterns: 
{enriched verbalization} 
--- 
Answer Format (SPARQL Generation): 
SPARQL: <place the generated SPARQL here in a single line> 

--- 
Answer Format (Path Expansion Selection): 
Indices: <place the comma-separated 0-index values of the paths to expand further for the answers, put at least one value. Do not pick too many.>
```


## Text Augmentation Prompt

Prompt for input text augmentation (based on [Vollmers et al. 2025](https://dl.acm.org/doi/10.1145/3731443.3771370)):

```text
Your task is to help to link information from questions to knowledge graphs. Please generate a list with all entities and types for the following question. Please generate one list with all entities. Do not format the json output.{question}
```