import json
import os
import glob

def read_json_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data

def save_json_file(json_obj, output_file_path):
    dir_name = os.path.dirname(output_file_path)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)
        
    with open(output_file_path, 'w', encoding='utf-8') as outfile:
        json.dump(json_obj, outfile, ensure_ascii=False, indent=4)


def build_annotation_map(source_file):
    """Build map from (dataset, split, qid, lang) -> annotations."""
    ann_map = {}
    with open(source_file, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            for src in item['sources']:
                key = (src['dataset'], src['split'], str(src['qid']), src['lang'])
                ann_map[key] = item['annotations']
    return ann_map


def extract_entities_relations(annotations):
    """Extract entities and relations lists from annotations."""
    entities = []
    relations = []
    for ann in annotations:
        uri = ann['identifier'].replace('wd:', '').replace('wdt:', '')
        label = ann['label']
        if ann['type'] == 'entity':
            entities.append({'label': label, 'uri': uri})
        elif ann['type'] == 'property':
            relations.append({'label': label, 'uri': uri})
    return entities, relations


def add_grasp_annotator(target_pattern, source_file, dry_run=True):
    ann_map = build_annotation_map(source_file)
    print(f"Loaded {len(ann_map)} annotation entries from {source_file}")

    target_files = sorted(glob.glob(target_pattern))
    print(f"Found {len(target_files)} target files")

    total_updated = 0
    total_questions = 0

    for target_file in target_files:
        data = read_json_file(target_file)
        parts = target_file.split(os.sep)
        dataset = parts[-3]
        split = parts[-2]

        file_updated = 0
        for question_item in data['questions']:
            total_questions += 1
            q_id = str(question_item['id'])
            languages = [q['language'] for q in question_item['question']]

            grasp_data = {}
            all_entities = []
            all_relations = []

            for lang in languages:
                key = (dataset, split, q_id, lang)
                if key in ann_map:
                    entities, relations = extract_entities_relations(ann_map[key])
                    grasp_data[lang] = {
                        'entities': entities,
                        'relations': relations
                    }
                    all_entities.extend(entities)
                    all_relations.extend(relations)

            if grasp_data:
                file_updated += 1
                question_item['grasp_el'] = grasp_data
                question_item['entities_aug_grasp_el'] = all_entities
                question_item['relations_aug_grasp_el'] = all_relations

        total_updated += file_updated
        print(f"  {target_file}: {file_updated}/{len(data['questions'])} questions would be updated")

        if not dry_run:
            save_json_file(data, target_file)
            print(f"  Saved {target_file}")

    print(f"\nTotal: {total_updated}/{total_questions} questions updated across {len(target_files)} files")


if __name__ == "__main__":
    # target_pattern = "data_dir/processed_kgqa_ds/*/*/tentrismain_aug_gold.json"
    # source = "data_dir/misc/all_annotated_combined.jsonl"
    target_pattern = "data_dir/processed_kgqa_ds/spinach/*/tentrismain_aug_gold.json"
    source = "data_dir/misc/spinach_annotated_combined.jsonl"
    add_grasp_annotator(target_pattern, source, dry_run=False)
