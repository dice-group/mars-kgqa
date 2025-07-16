# Sample usage: python -m src.example.openai_api_call
from openai import OpenAI
from src.const.llm import GEMMA3_CONFIG

OPAI_CLIENT = OpenAI(base_url=GEMMA3_CONFIG.endpoint, api_key=GEMMA3_CONFIG.api_key)

MODEL_ID=GEMMA3_CONFIG.model_id

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
