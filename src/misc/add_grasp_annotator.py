import json
import os

def read_json_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data

def save_json_file(json_obj, output_file_path):
    # Create directory if not exists
    dir_name = os.path.dirname(output_file_path)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)
        
    with open(output_file_path, 'w', encoding='utf-8') as outfile:
        json.dump(json_obj, outfile, ensure_ascii=False, indent=4)


def add_grasp_annotator(target_file, source_file):
    # Load target JSON
    data = read_json_file(target_file)
    
    # Load source JSONL into a map
    grasp_map = {}
    with open(source_file, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            grasp_map[str(item['id'])] = item['annotations']

    for question_item in data['questions']:
        q_id = str(question_item['id'])
        if q_id in grasp_map:
            annotations = grasp_map[q_id]
            
            entities = []
            relations = []
            
            for ann in annotations:
                # Strip wd: or wdt: from identifier
                uri = ann['identifier'].replace('wd:', '').replace('wdt:', '')
                label = ann['label']
                
                if ann['type'] == 'entity':
                    entities.append({'label': label, 'uri': uri})
                elif ann['type'] == 'property':
                    relations.append({'label': label, 'uri': uri})
            
            # Get languages present in the question
            languages = [q['language'] for q in question_item['question']]
            
            grasp_data = {}
            for lang in languages:
                grasp_data[lang] = {
                    'entities': entities,
                    'relations': relations
                }
            
            question_item['grasp'] = grasp_data
            question_item['entities_aug_grasp'] = entities
            question_item['relations_aug_grasp'] = relations
            
    save_json_file(data, target_file)
    print(f"Successfully added grasp annotator to {target_file}")

if __name__ == "__main__":
    target = "data_dir/processed_kgqa_ds/qald10/test/tentrismain_aug_gold.json"
    source = "data_dir/misc/qald10_grasp_annotated.jsonl"
    add_grasp_annotator(target, source)
