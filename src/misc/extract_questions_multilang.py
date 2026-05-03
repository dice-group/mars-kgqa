import json
import glob
import os
from collections import defaultdict


def build_question_map(input_pattern, output_file):
    question_map = defaultdict(list)

    files = sorted(glob.glob(input_pattern))
    print(f"Found {len(files)} input files")

    for filepath in files:
        parts = filepath.split(os.sep)
        dataset = parts[-3]
        split = parts[-2]

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for q in data.get('questions', []):
            qid = str(q['id'])

            # Original question strings per language
            for lang_obj in q.get('question', []):
                text = lang_obj.get('string', '').strip()
                lang = lang_obj.get('language')
                if text:
                    question_map[text].append((dataset, split, qid, lang, False))

            # English translations — skip "en" since translation of an English question is redundant
            for lang, trans_text in q.get('translations', {}).items():
                if lang == 'en':
                    continue
                text = trans_text.strip()
                if text:
                    question_map[text].append((dataset, split, qid, lang, True))

    # Stats
    total_refs = sum(len(v) for v in question_map.values())
    multi = sum(1 for v in question_map.values() if len(v) > 1)
    print(f"Unique texts: {len(question_map)}, Total refs: {total_refs}, Multi-source: {multi}")

    # Save
    serializable = {k: [list(m) for m in v] for k, v in question_map.items()}
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"Saved to {output_file}")


if __name__ == "__main__":
    # input_pattern = "/local/nikit/repos/mars-kgqa/data_dir/processed_kgqa_ds/*/*/tentrismain_aug_gold.json"
    # output_path = "/local/nikit/repos/mars-kgqa/data_dir/misc/question_map.json"
    input_pattern = "/local/nikit/repos/mars-kgqa/data_dir/processed_kgqa_ds/spinach/*/tentrismain_aug_gold.json"
    output_path = "/local/nikit/repos/mars-kgqa/data_dir/misc/spinach_question_map.json"
    build_question_map(input_pattern, output_path)
