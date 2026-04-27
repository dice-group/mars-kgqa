import os
from enum import Enum
from src.util.llm import get_opai_client
from src.const.misc import NOMIC_V2_TOKENIZER


MAGISTRAL_2509_SYS_PROMPT = """First draft your thinking process (inner monologue) until you arrive at a response. Format your response using Markdown, and use LaTeX for any mathematical equations. Write both your thoughts and the response in the same language as the input.

Your thinking process must follow the template below:[THINK]Your thoughts or/and draft, like working through an exercise on scratch paper. Be as casual and as long as you want until you are confident to generate the response. Use the same language as the input.[/THINK]Here, provide a self-contained response.
"""

class ModelAPIConfig:
    
    def __init__(self, model_id, endpoint, api_key, sysprompt=None, postfix=None, max_len=None, tokenizer=None):
        self.model_id = model_id
        self.endpoint = endpoint
        self.api_key = api_key
        self.sysprompt = sysprompt
        self.postfix = postfix
        self.max_len = max_len
        self.tokenizer = tokenizer
        
    def get_static_instance(self):
        if not hasattr(self, 'static_instance'):
            self.static_instance = self.get_new_instance()
        return self.static_instance
    
    def get_new_instance(self):
        return get_opai_client(self.endpoint, self.api_key)
    
    def to_dict(self):
        """Convert the configuration to a JSON-serializable dictionary."""
        return {
            'model_id': self.model_id,
            'endpoint': self.endpoint,
            'api_key': self.api_key,
            'sysprompt': self.sysprompt,
            'postfix': self.postfix
        }
    
LLM_ENDPOINT = os.environ.get("LLAMA_SERVER_OPENAI_ENDPOINT")
LLM_API_KEY = os.environ.get("OWUI", "no-api-key")

# Chat models enum to keep a single (iterable) collection and prevent reassignment        
class ChatModel(Enum):
    # All models are using Q8
    GEMMA3 = ModelAPIConfig("gemma-3-27b-it", LLM_ENDPOINT, LLM_API_KEY) # Gets stuck on being provided large > 10 top-N context
    QWEN3 = ModelAPIConfig("qwen3-32b", LLM_ENDPOINT, LLM_API_KEY) # Works
    MISTRAL3 = ModelAPIConfig("mistral-small-3.2-24b", LLM_ENDPOINT, LLM_API_KEY)
    GPTOSS120B = ModelAPIConfig("gpt-oss-120b", LLM_ENDPOINT, LLM_API_KEY) # Works
    # GLM4dt5AIR = ModelAPIConfig("glm-4.5-air", LLM_ENDPOINT, LLM_API_KEY) # Takes too long thinking, causes: "openai.APITimeoutError: Request timed out."
    GLM4dt5AIR_Nothink = ModelAPIConfig("glm-4.5-air", LLM_ENDPOINT, LLM_API_KEY, None, "/no_think") # Does not think # But is still taking too long for some prompts, which causes: "openai.APITimeoutError: Request timed out."
    QWEN3_CODER = ModelAPIConfig("qwen3-coder-30b-a3b", LLM_ENDPOINT, LLM_API_KEY)
    DEEPSEEK_R1_QWEN3_8B = ModelAPIConfig("deepseek-r1-0528-qwen3-8b", LLM_ENDPOINT, LLM_API_KEY)
    LLAMA_NEMOTRON_SUPER_49B = ModelAPIConfig("llama-3_3-nemotron-super-49b-v1_5", LLM_ENDPOINT, LLM_API_KEY, "/no_think") # Thinking model is taking too long, almost stuck at every request # Even normal model gets stuck
    LLAMA4_SCOUT_17B16E = ModelAPIConfig("llama-4-scout-17b-16e-instruct", LLM_ENDPOINT, LLM_API_KEY, "If a format is given, stick to it strictly and do NOT add any explanation to it. The outputs for provided formats will be machine processed and require strict adherence to match pattern.") # Adding system prompt to stop this model from writing extra explanations
    MAGISTRAL_SMALL_2509 = ModelAPIConfig("magistral-small-2509", LLM_ENDPOINT, LLM_API_KEY, MAGISTRAL_2509_SYS_PROMPT)
    GRANITE_4H_SM = ModelAPIConfig("granite-4.0-h-small", LLM_ENDPOINT, LLM_API_KEY, "If a format is given, stick to it strictly and do NOT add anything outside the format. If there are multiple formats, strictly follow only one, do NOT add multiple formats together.")
    NEMOTRON3SUPER = ModelAPIConfig("nemotron-3-super-120B-a12b", LLM_ENDPOINT, LLM_API_KEY) # Works
    GEMMA4_31B = ModelAPIConfig("gemma-4-31b", LLM_ENDPOINT, LLM_API_KEY) # WIP
    QWEN3D5_122B = ModelAPIConfig("qwen3d5-122B-a10b", LLM_ENDPOINT, LLM_API_KEY) # WIP

# Embedding model
class EmbeddingModel(Enum):
    NOMICV2_CONFIG = ModelAPIConfig("nomic-embed-text-v2-moe", LLM_ENDPOINT, LLM_API_KEY, max_len=512, tokenizer=NOMIC_V2_TOKENIZER)

DEFAULT_CHAT_LLM_CONFIG = ChatModel.GEMMA3.value # can be changed later
DEFAULT_EMBED_LLM_CONFIG = EmbeddingModel.NOMICV2_CONFIG.value


