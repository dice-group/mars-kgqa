import os

class ModelAPIConfig:
    def __init__(self, model_id, endpoint, api_key):
        self.model_id = model_id
        self.endpoint = endpoint
        self.api_key = api_key

# Chat models
GEMMA3_CONFIG = ModelAPIConfig("gemma-3-27b-it", os.environ.get("GEMMA3_OPENAI_ENDPOINT"), os.environ.get("OWUI"))

QWEN3_CONFIG = ModelAPIConfig("Qwen3-32B", os.environ.get("QWEN3_OPENAI_ENDPOINT"), os.environ.get("OWUI"))

MISTRAL3_CONFIG = ModelAPIConfig("Mistral-Small-3.2-24B-Instruct-2506", os.environ.get("MISTRAL3_OPENAI_ENDPOINT"), os.environ.get("OWUI"))

# Embedding model
NOMICV2_CONFIG = ModelAPIConfig("nomic-embed-text-v2-moe", os.environ.get("NOMICV2_OPENAI_ENDPOINT"), os.environ.get("OWUI"))