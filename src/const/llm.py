import os
from enum import Enum
from src.util.llm import get_opai_client

class ModelAPIConfig:
    
    def __init__(self, model_id, endpoint, api_key, sysprompt=None):
        self.model_id = model_id
        self.endpoint = endpoint
        self.api_key = api_key
        self.sysprompt = sysprompt
        
    def get_static_instance(self):
        if not hasattr(self, 'static_instance'):
            self.static_instance = self.get_new_instance()
        return self.static_instance
    
    def get_new_instance(self):
        return get_opai_client(self.endpoint, self.api_key)
    

LLM_ENDPOINT = os.environ.get("LLAMA_SWAP_OPENAI_ENDPOINT")
# Chat models enum to keep a single (iterable) collection and prevent reassignment        
class ChatModel(Enum):
    # All models are using Q8
    GEMMA3 = ModelAPIConfig("gemma-3-27b-it", LLM_ENDPOINT, os.environ.get("OWUI"))
    QWEN3 = ModelAPIConfig("qwen3-32b", LLM_ENDPOINT, os.environ.get("OWUI"))
    MISTRAL3 = ModelAPIConfig("mistral-small-3.2-24b", LLM_ENDPOINT, os.environ.get("OWUI"))
    GPTOSS120B = ModelAPIConfig("gpt-oss-120b", LLM_ENDPOINT, os.environ.get("OWUI"))
    GLM4dt5AIR = ModelAPIConfig("glm-4.5-air", LLM_ENDPOINT, os.environ.get("OWUI")) # Takes too long thinking
    QWEN3_CODER = ModelAPIConfig("qwen3-coder-30b-a3b", LLM_ENDPOINT, os.environ.get("OWUI"))
    DEEPSEEK_R1_QWEN3_8B = ModelAPIConfig("deepseek-r1-0528-qwen3-8b", LLM_ENDPOINT, os.environ.get("OWUI"))
    LLAMA_NEMOTRON_SUPER_49B = ModelAPIConfig("llama-3_3-nemotron-super-49b-v1_5", LLM_ENDPOINT, os.environ.get("OWUI"), "/no_think") # Thinking model is taking too long, almost stuck at every request
    

# Embedding model
class EmbeddingModel(Enum):
    NOMICV2_CONFIG = ModelAPIConfig("nomic-embed-text-v2-moe", LLM_ENDPOINT, os.environ.get("OWUI"))

DEFAULT_CHAT_LLM_CONFIG = ChatModel.GEMMA3.value # can be changed later
DEFAULT_EMBED_LLM_CONFIG = EmbeddingModel.NOMICV2_CONFIG.value