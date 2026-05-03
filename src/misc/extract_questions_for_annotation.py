import json

DATASET_ORDER = {"qald9plus": 0, "qald10": 1, "lcquad2": 2}


def generate_jsonl(map_file, output_file):
    with open(map_file, 'r', encoding='utf-8') as f:
        question_map = json.load(f)

    seen = set()
    entries = []

    for text, sources in question_map.items():
        filtered = []
        for s in sources:
            dataset, split, qid, lang, is_translated = s
            if lang == "en" or is_translated:
                key = (dataset, split, qid, lang, is_translated)
                if key not in seen:
                    seen.add(key)
                    filtered.append({
                        "dataset": dataset,
                        "split": split,
                        "qid": qid,
                        "lang": lang,
                        "is_translated": is_translated
                    })

        if filtered:
            entries.append({"question": text, "sources": filtered})

    entries.sort(key=lambda e: DATASET_ORDER.get(e["sources"][0]["dataset"], 99))

    with open(output_file, 'w', encoding='utf-8') as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"Wrote {len(entries)} lines to {output_file}")


if __name__ == "__main__":
    # map_path = "/local/nikit/repos/mars-kgqa/data_dir/misc/question_map.json"
    # output_path = "/local/nikit/repos/mars-kgqa/data_dir/misc/questions_for_annotation.jsonl"
    map_path = "/local/nikit/repos/mars-kgqa/data_dir/misc/spinach_question_map.json"
    output_path = "/local/nikit/repos/mars-kgqa/data_dir/misc/spinach_questions_for_annotation.jsonl"
    generate_jsonl(map_path, output_path)
