# Sample usage: python -m src.example.embedding_api_call
# Example inspired from: https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe-GGUF
import requests
from src.const.llm import DEFAULT_EMBED_LLM_CONFIG
from src.util.common import dot

def embed(texts):
    resp = requests.post(DEFAULT_EMBED_LLM_CONFIG.endpoint + '/embeddings', json={'input': texts}).json()
    return [d['embedding'] for d in resp['data']]


docs = ['Angela Merkel place of birth Eimsbüttel', 'Angel Merkel father Horst Kasner']
docs_embed = embed([d for d in docs])

query = 'What is the birthplace of Angela Merkel?'
query_embed = embed([query])[0]
print(f'query: {query!r}')
for d, e in zip(docs, docs_embed):
    print(f'similarity {dot(query_embed, e):.2f}: {d!r}')