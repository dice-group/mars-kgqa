from openai import OpenAI
import requests
import re
import copy
import json
import time
from src.const.misc import LLAMA_SERVER_ENDPOINT, LLAMA_MAX_CTX, RUN_STATS, LLAMA_CONTAINER_NAME, SLURM_ACTIVE
from src.util.common import kill_container

def get_opai_client(endpoint=None, api_key=None):
    opai_client = OpenAI(base_url=endpoint, api_key=api_key)
    return opai_client

# Function to send batches to OpenAI API
def prompt_chat_llm(user_prompt, sys_prompt, client_instance, model_id, postfix=None):
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
    except Exception as e:
        # Write the prompt to a temporary file if an exception occurs
        print(f'Failed for message: {message_list}')
        RUN_STATS["failure_count"] += 1
        kill_container(LLAMA_CONTAINER_NAME, use_apptainer=SLURM_ACTIVE)
        print(f'Waiting for llama-server to restart...')
        time.sleep(10)
        # raise e
        return " ", " "
    # Extract the analysis from theresponse
    
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

def get_ctx_size(model_id, llama_server_ep):
    response = requests.get(llama_server_ep + "/models")
    response.raise_for_status()
    data = response.json()

    for model in data["data"]:
        if model["id"] == model_id:
            args = model["status"]["args"]
            for i, arg in enumerate(args):
                if arg == "--ctx-size" and i + 1 < len(args):
                    return int(args[i + 1])
    return None

def _preprocess_input(input_texts, tokenizer, limit, model_id):
    batch_to_decode = []
    batch_index = []
    final_texts = copy.deepcopy(input_texts)
    # Truncate only those that might be bigger
    for i, input_item in enumerate(input_texts):
        
        if len(input_item) * 2 > limit: # arbitrary logic, but should work as an underestimated threshold
            tokens = tokenize_content(input_item, model_id, LLAMA_SERVER_ENDPOINT)
            input_len = len(tokens)
            if input_len > limit: # actual limit check
                batch_to_decode.append(tokens[:limit])
                batch_index.append(i)
    
    if len(batch_to_decode) > 0:
        #encoded_input = tokenizer(batch_to_decode, padding=True, truncation=True, return_tensors='pt')
        decoded_texts = tokenizer.batch_decode(batch_to_decode, skip_special_tokens=True)
        
        for ind, dec_text in zip(batch_index, decoded_texts):
            final_texts[ind] = dec_text
    
    return final_texts

def get_embeddings(input_texts, embed_config=None):
    # preprocess input beforehand
    prep_input_texts = _preprocess_input(input_texts, embed_config.tokenizer, embed_config.max_len, embed_config.model_id)
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