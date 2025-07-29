# Sample usage: python -m src.example.openai_api_call
from openai import OpenAI
from src.const.llm import DEFAULT_CHAT_LLM_CONFIG

OPAI_CLIENT = OpenAI(base_url=DEFAULT_CHAT_LLM_CONFIG.endpoint, api_key=DEFAULT_CHAT_LLM_CONFIG.api_key)

MODEL_ID=DEFAULT_CHAT_LLM_CONFIG.model_id

completion = OPAI_CLIENT.chat.completions.create(
    model=MODEL_ID,
    messages=[
        {"role": "system", "content": "Talk like a pirate."},
        {
            "role": "user",
            "content": "How do I check if a Python object is an instance of a class?",
        },
    ],
)

print(completion.choices[0].message.content)
