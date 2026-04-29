import json

def extract_questions(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    questions = data.get('questions', [])
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for q in questions:
            # Extract English question
            en_question = None
            for lang_obj in q.get('question', []):
                if lang_obj.get('language') == 'en':
                    en_question = lang_obj.get('string')
                    break
            
            if en_question is not None:
                # Format ID as q01, q02... (1-based indexing)
                q_id = str(q['id'])
                line = json.dumps({"id": q_id, "question": en_question}, ensure_ascii=False)
                f.write(line + '\n')

if __name__ == "__main__":
    input_path = "/local/nikit/repos/mars-kgqa/data_dir/processed_kgqa_ds/qald10/test/tentrismain_aug_gold.json"
    output_path = "qald10_questions.jsonl"
    extract_questions(input_path, output_path)
    print(f"Successfully extracted questions to {output_path}")
