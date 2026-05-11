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
