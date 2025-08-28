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
            messages=message_list
        )
    except Exception as e:
        # Write the prompt to a temporary file if an exception occurs
        print('Failed for message: {message_list}')
        raise e
    # Extract the analysis from theresponse
    model_res_text = completion.choices[0].message.content
    return model_res_text

def get_embeddings(input_texts, embed_config=None):
    # Compute input embeddings
    embed_endpoint = embed_config.endpoint
    resp = requests.post(embed_endpoint + '/embeddings', json={'input': input_texts, 'model': embed_config.model_id}).json()
    return [d['embedding'] for d in resp['data']]

def remove_think_context(llm_response_text):
    # Remove the parts between <think> </think> if its there, other return as is
    # Use a non‑greedy regex with DOTALL so it matches across newlines.
    cleaned_text = re.sub(r'<think\b[^>]*?>.*?</think>', '', llm_response_text, flags=re.DOTALL)
    return cleaned_text