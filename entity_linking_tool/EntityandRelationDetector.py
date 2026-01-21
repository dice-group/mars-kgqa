from transformers import T5Tokenizer, T5ForConditionalGeneration
from data_processing import Dataprocessor_test
import json
import torch
import pickle
import re
from tqdm import tqdm
class EntityAndRelationDetector():
    def __init__(self,params):
        self.device = "cuda:"+str(params["cuda_device_id"]) if torch.cuda.is_available() else "cpu"
        self.tokenizer = T5Tokenizer.from_pretrained(params["tokenizer_name"]if params["tokenizer_name"]
                                                     else params["model_name"])
        self.dp = Dataprocessor_test(self.tokenizer, "")

        self.model = T5ForConditionalGeneration.from_pretrained(params["parameter_path_prefix"]
                                                                +params["pretrained_model_path"])
        self.model.to(self.device)

        self.relations=pickle.load(open(params["parameter_path_prefix"]+params["relation_dict_file"],"rb"))
        self.entities=pickle.load(open(params["parameter_path_prefix"]+params["entity_dict_file"],"rb"))




    def predict(self,sentence):
        i = self.dp.process_sample(sentence+"[SEP]target_wikidata").input_ids
        out = self.model.generate(input_ids=i.to(self.device), max_length=650)
        #out = self.model.generate(input_ids=i.to(self.device), max_length=650,
        #                          prefix_allowed_tokens_fn=self.prefix_allowed_tokens_fn)
        out_str=self.tokenizer.decode(out[0], skip_special_tokens=True)
        # print(out_str)
        try:
            entstr=out_str[out_str.index("entities: ")+len("entities: "):out_str.index(", relations")]
            all_ents=re.findall(r"\[BEG\]([^\[]+)\[END\]",entstr)
            '''
            sp=entstr.split("[END] , [BEG]")
            all_ents=[el.replace("[BEG]","").replace("[END]","")for el in entstr.split("[END] , [BEG]")]
            '''
            relations_str = out_str[out_str.index("relations: ") + len("relations: "):-1]
            all_relations = re.findall(r"\[BEG\]([^\[]+)\[END\]", relations_str)
            #all_relations = [el.replace("[BEG]","").replace("[END]","")for el in relations_str.split("[END] , [BEG]")]
        except:
            print("failed")
            all_ents=[]
            all_relations=[]
        # ent=[{"label":el,"uri":self.entities[el]}for el in all_ents if el in self.entities]
        # rel=[{"label":el,"uri":self.relations[el]}for el in all_relations if el in self.relations]
        return [{"label":el,"uri":self.entities[el]}for el in all_ents if el in self.entities],\
               [{"label":el,"uri":self.relations[el]}for el in all_relations if el in self.relations]