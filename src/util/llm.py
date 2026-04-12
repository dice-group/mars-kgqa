from openai import OpenAI
import requests
import re
import copy
import time
import json
from src.const.misc import LLAMA_SERVER_ENDPOINT, LLAMA_MAX_CTX

def get_opai_client(endpoint=None, api_key=None):
    opai_client = OpenAI(base_url=endpoint, api_key=api_key)
    return opai_client

# Function to send batches to OpenAI API
def prompt_chat_llm(user_prompt, sys_prompt, client_instance, model_id, postfix=None, max_retries=3):
    message_list = []
    if sys_prompt:
        message_list.append({"role": "system", "content": sys_prompt})
    message_list.append({"role": "user", "content": f'{user_prompt} {postfix}' if postfix else user_prompt})
    
    # check tokens
    message_str = " ".join([str(item) for item in message_list])
    tokens = tokenize_content(message_str, model_id, LLAMA_SERVER_ENDPOINT)
    total_len = len(tokens)
    print(f'Total tokens in the message: {total_len}')
    
    if total_len > LLAMA_MAX_CTX:
        print(f'Context size exceeded for message: {message_list}')
        print('Returning empty values!')
        return " ", " "

    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            # Call the OpenAI API
            completion = client_instance.chat.completions.create(
                model=model_id,
                messages=message_list,
                extra_body={
                    "seed": 42,
                    "cache_prompt": False
                }
            )
            break  # Success — exit the retry loop
        except Exception as e:
            last_exception = e
            print(f'Attempt {attempt}/{max_retries} failed for message: {message_list}')
            if attempt < max_retries:
                wait = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s...
                print(f'Retrying in {wait}s...')
                time.sleep(wait)
            else:
                print('All retries exhausted.')
                raise last_exception

    # Extract the analysis from the response
    model_msg = completion.choices[0].message
    model_res_text = model_msg.content

    # Extract reasoning or thinking context separately
    reasoning_content = model_msg.model_extra.get('reasoning_content')
    if not reasoning_content:
        model_res_text, reasoning_content = remove_think_context(model_res_text)
    return model_res_text, reasoning_content

def tokenize_content(content, model_id, llama_server_ep):
    
    payload = json.dumps({
        "content": content,
        "model": model_id
    })
    
    headers = {
        'Content-Type': 'application/json'
    }

    response = requests.post(llama_server_ep + '/tokenize', headers=headers, data=payload)
    # Raise an exception for 4xx or 5xx status codes
    response.raise_for_status() 
    
    data = response.json()
    return data.get("tokens")

# TODO: Try to find a better way to truncate automatically
def _preprocess_input(input_texts, tokenizer, limit):
    batch_to_encode = []
    batch_index = []
    final_texts = copy.deepcopy(input_texts)
    # Truncate only those that might be bigger
    for i, input_item in enumerate(input_texts):
        if len(input_item) * 2 > limit: # arbitrary logic, but should work as an underestimated threshold
            batch_to_encode.append(input_item)
            batch_index.append(i)
    
    if len(batch_to_encode) > 0:
        encoded_input = tokenizer(batch_to_encode, padding=True, truncation=True, return_tensors='pt')
        decoded_texts = tokenizer.batch_decode(encoded_input['input_ids'], skip_special_tokens=True)
        
        for ind, dec_text in zip(batch_index, decoded_texts):
            final_texts[ind] = dec_text
    
    return final_texts

def get_embeddings(input_texts, embed_config=None):
    # preprocess input beforehand
    prep_input_texts = _preprocess_input(input_texts, embed_config.tokenizer, embed_config.max_len)
    # Compute input embeddings
    embed_endpoint = embed_config.endpoint
    resp = requests.post(embed_endpoint + '/embeddings', json={'input': prep_input_texts, 'model': embed_config.model_id}).json()
    return [d['embedding'] for d in resp['data']]

def remove_think_context(llm_response_text):
    # Remove the parts between <think> </think> if it's there,
    # and also return the extracted thinking content.
    # Use a non‑greedy regex with DOTALL so it matches across newlines.
    think_parts = re.findall(r'(<think\b[^>]*?>.*?</think>)', llm_response_text, flags=re.DOTALL)

    # Strip out the thinking blocks from the original response
    cleaned_text = re.sub(r'<think\b[^>]*?>.*?</think>', '', llm_response_text, flags=re.DOTALL)

    # Return a tuple: (cleaned text, concatenated thinking content)
    # If no <think> block was found, think_parts will be an empty list.
    return cleaned_text, ''.join(think_parts)