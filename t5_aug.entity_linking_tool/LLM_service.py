import requests
import ollama


class Local_service:
    def __init__(self,model="llama3:70b"):
        self.model=model
    def run_expansion_request(self,sent:str,spans):
        req = f'''
                    Given the sentence {sent} and the spans {spans}. Can you map each of the given spans to its likely entity in wikipedia and return a valid json document using the keys "span" and "entity_name" please do not format the json output?
                '''
        response = ollama.chat(model=self.model, messages=[
            {
                'role': 'user',
                'content': req,
            },
        ])
        return response['message']['content']
    def run_ner_request(self,sentence:str):
        #req="Please generate one list with all entities and wikidata types from the following text in JSON format including. excluding numbers. Do not format the json output."+ sentence
        req = "Your task is to help to link Information from Questions to Knowledge Graphs. Please generate a list with all terms, that have to searched on Wikidata KB including entities, types and relations. Please generate one list with all terms in json format. Do not format the json output." + sentence
        try:
            response = ollama.chat(model=self.model, messages=[
                {
                    'role': 'user',
                    'content': req,
                },
            ])
            return response['message']['content']
        except Exception as e:
            print("failed"+sentence)
            return ""

    def run_filter_request(self,sentence:str,entities:str,relations:str):
        #req="Please generate one list with all entities and wikidata types from the following text in JSON format including. excluding numbers. Do not format the json output."+ sentence
        req = f"""Your task is to help to link Information from Questions to Knowledge Graphs. 
From the following list of entities: {entities}.
And the following list of relations: {relations}.
Which of them are required to write a SPARQL query to answer the question: {sentence} Please return as less entities and relations as possible. 
Please return only the IDs of the entities and relations. """
        try:
            response = ollama.chat(model=self.model, messages=[
                {
                    'role': 'user',
                    'content': req,
                },
            ])
            return response['message']['content']
        except Exception as e:
            print("failed"+sentence)
            return ""

    def expand_ner_request(self,sentence:str):
        #req="In the following text there are already annotated entities, if the text contains more entities, please provide a list with only those entities in json format. Do not format the JSON output. "+ sentence
        req = "Your task is to help to link Information from Questions to Knowledge Graphs. Please generate a list with all Entities, relations and Types for the following Question. Please generate one list with all entities . Do not format the json output." + sentence
        response = ollama.chat(model=self.model, messages=[
            {
                'role': 'user',
                'content': req,
            },
        ])
        return response['message']['content']