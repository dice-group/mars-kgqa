from openai import OpenAI

def get_opai_client(endpoint=None, api_key=None):
    opai_client = OpenAI(base_url=endpoint, api_key=api_key)
    return opai_client

# Function to send batches to OpenAI API
def send_to_llm(prompt, client_instance, model_id):
    try:
        # Call the OpenAI API
        completion = client_instance.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        # Write the prompt to a temporary file if an exception occurs
        print('Failed for prompt: {prompt}')
        raise e
    # Extract the analysis from theresponse
    model_res_text = completion.choices[0].message.content
    return model_res_text