import requests

def dot(va, vb):
    return sum(a * b for a, b in zip(va, vb))

def embed(texts):
    resp = requests.post('http://localhost:8080/v1/embeddings', json={'input': texts}).json()
    return [d['embedding'] for d in resp['data']]

docs = ['嵌入很酷', '骆驼很酷']  # 'embeddings are cool', 'llamas are cool'
docs_embed = embed(['search_document: ' + d for d in docs])

query = '跟我讲讲嵌入'  # 'tell me about embeddings'
query_embed = embed(['search_query: ' + query])[0]
print(f'query: {query!r}')
for d, e in zip(docs, docs_embed):
    print(f'similarity {dot(query_embed, e):.2f}: {d!r}')