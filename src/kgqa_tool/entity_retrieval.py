from src.const.llm import DEFAULT_CHAT_LLM_CONFIG
from src.kgqa_tool.llm_request import recognize_entities_and_relations

# Find all the entity mentions in a given query and also which languages in addition to English should we be looking at.

def get_llm_augmented_input(input, model_config=DEFAULT_CHAT_LLM_CONFIG):
    llm_response = recognize_entities_and_relations(input, model_config)
    # TODO: @Daniel write postprocessing logic here
    raise NotImplementedError()

def find_entities_and_relations(input, model_config=DEFAULT_CHAT_LLM_CONFIG):
    # Send the input to LLM
    aug_text = get_llm_augmented_input(input, model_config)
    # TODO: @Daniel Write rest of the logic to retrieve entities and relations here
    raise NotImplementedError()