from openai import OpenAI
from src.const.llm import DEFAULT_EMBED_LLM_CONFIG

def get_opai_client(endpoint=None, api_key=None):
    opai_client = OpenAI(base_url=endpoint, api_key=api_key)
    return opai_client

# Function to send batches to OpenAI API
def prompt_chat_llm(user_prompt, sys_prompt, client_instance, model_id):
    message_list = []
    if sys_prompt:
        message_list.append({"role": "system", "content": sys_prompt})
    message_list.append({"role": "user", "content": user_prompt})
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

def get_embeddings(input_list, embed_config=DEFAULT_EMBED_LLM_CONFIG):
    # TODO: Compute input embeddings
    raise NotImplementedError()