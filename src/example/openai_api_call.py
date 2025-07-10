# Sample usage: python -m src.example.openai_api_call
import os
from openai import OpenAI

OPAI_CLIENT = OpenAI(base_url=os.environ.get("OPENAI_LLM_ENDPOINT"), api_key=os.environ.get("OWUI"))

MODEL_ID="gemma-3-27b-it"

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
