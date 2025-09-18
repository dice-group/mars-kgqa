from openai import OpenAI
import requests
import re

def get_opai_client(endpoint=None, api_key=None):
    opai_client = OpenAI(base_url=endpoint, api_key=api_key)
    return opai_client

# Function to send batches to OpenAI API
def prompt_chat_llm(user_prompt, sys_prompt, client_instance, model_id, postfix=None):
    message_list = []
    if sys_prompt:
        message_list.append({"role": "system", "content": sys_prompt})
    message_list.append({"role": "user", "content": f'{user_prompt} {postfix}' if postfix else user_prompt})
    try:
        # Call the OpenAI API
        completion = client_instance.chat.completions.create(
            model=model_id,
            messages=message_list,
            extra_body={
                "seed":42,
                "cache_prompt":False
            }
        )
    except Exception as e:
        # Write the prompt to a temporary file if an exception occurs
        print('Failed for message: {message_list}')
        raise e
    # Extract the analysis from theresponse
    
    model_msg = completion.choices[0].message
    
    model_res_text = model_msg.content
    
    # Extract reasoning or thinking context separately
    reasoning_content = model_msg.model_extra.get('reasoning_content')
    if not reasoning_content:
        model_res_text, reasoning_content = remove_think_context(model_res_text)
    return model_res_text, reasoning_content

def get_embeddings(input_texts, embed_config=None):
    # Compute input embeddings
    embed_endpoint = embed_config.endpoint
    resp = requests.post(embed_endpoint + '/embeddings', json={'input': input_texts, 'model': embed_config.model_id}).json()
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