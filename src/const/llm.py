import os
from enum import Enum
from src.util.llm import get_opai_client

class ModelAPIConfig:
    def __init__(self, model_id, endpoint, api_key):
        self.model_id = model_id
        self.endpoint = endpoint
        self.api_key = api_key
        
    def get_static_instance(self):
        if not hasattr(self, 'static_instance'):
            self.static_instance = self.get_new_instance()
        return self.static_instance
    
    def get_new_instance(self):
        return get_opai_client(self.endpoint, self.api_key)    

# Chat models        
class ChatModels(Enum):
    GEMMA3 = ModelAPIConfig("gemma-3-27b-it", os.environ.get("GEMMA3_OPENAI_ENDPOINT"), os.environ.get("OWUI"))
    QWEN3 = ModelAPIConfig("Qwen3-32B", os.environ.get("QWEN3_OPENAI_ENDPOINT"), os.environ.get("OWUI"))
    MISTRAL3 = ModelAPIConfig("Mistral-Small-3.2-24B-Instruct-2506", os.environ.get("MISTRAL3_OPENAI_ENDPOINT"), os.environ.get("OWUI"))

# Embedding model
class EmbeddingModels(Enum):
    NOMICV2_CONFIG = ModelAPIConfig("nomic-embed-text-v2-moe", os.environ.get("NOMICV2_OPENAI_ENDPOINT"), os.environ.get("OWUI"))

DEFAULT_CHAT_LLM_CONFIG = ChatModels.GEMMA3.value # can be changed later
DEFAULT_EMBED_LLM_CONFIG = EmbeddingModels.NOMICV2_CONFIG.value