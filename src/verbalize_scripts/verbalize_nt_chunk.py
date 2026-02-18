import argparse
import pickle
import sys
from tqdm import tqdm
from src.verbalize_scripts.label_map_gen import _decode_escaped, _uri_last_part
from src.util.common import create_directory_if_not_exists

## Sample usage: bash pylauncher.sh normal src.verbalize_scripts.verbalize_nt_chunk /scratch/hpc-prf-merlin/project_data/wikidata_qald10_dump/2000_chunks/dataset_chunk_0926.nt data_dir/verbalization/label_map.pkl -o data_dir/verbalization/2000_chunks/dataset_chunk_0926.txt

LABEL_EXTENSION = {'description': 'description@en'}  # Accomodate http://schema.org/description

def _parse_nt_line(line: str):
    """
    Very lightweight N‑Triples parser.
    Returns (subject_uri, predicate_uri, object) where object is either
    a URI string or a literal (including its language tag, e.g. "foo"@en).
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None, None, None

    # Split on whitespace, but keep quoted literals intact.
    parts = []
    buf = ""
    in_literal = False
    for ch in line:
        if ch == '"' and not in_literal:
            in_literal = True
        elif ch == '"' and in_literal:
            in_literal = False
        if ch.isspace() and not in_literal:
            if buf:
                parts.append(buf)
                buf = ""
        else:
            buf += ch
    if buf:
        parts.append(buf)

    # Expected pattern: <s> <p> <o> .
    if len(parts) < 4 or parts[-1] != ".":
        return None, None, None

    subj = parts[0].strip("<>")
    pred = parts[1].strip("<>")
    obj = " ".join(parts[2:-1])  # keep literal language tags intact
    return subj, pred, obj


def _extract_label(label_map, uri):
    """Return a dict {lang: label_text} for the given URI (using last‑part key)."""
    key = _uri_last_part(uri)
    raw = label_map.get(key, [])
    result = {}
    for entry in raw:
        if "@" in entry:
            txt, lang = entry.rsplit("@", 1)
            result[lang] = txt
        else:
            result[""] = entry
    return result


def _is_literal(obj):
    """Detect N‑Triples literals – they start with a quote."""
    return obj.startswith('"')


def _strip_literal_lang(lit):
    """
    Given a literal like '"hello world"@en' return ('hello world', 'en')
    If no lang tag, returns ('hello world', '').
    """
    if not lit.startswith('"'):
        return lit, ""
    end = lit.rfind('"')
    value = lit[1:end]
    rest = lit[end + 1 :].strip()
    lang = ""
    if rest.startswith("@"):
        lang = rest[1:].split()[0]
    return value, lang


# Core verbalisation generator
def verbalize(
    nt_path: str,
    label_map_path: str,
    buffer_gb: float = 1.0,
    progress: bool = True,
):
    """
    Yield **(sentence, triple)** tuples.

    * ``sentence`` – the human‑readable verbalisation string.
    * ``triple``  – a ``(subject_uri, predicate_uri, object_raw)`` tuple
      that produced the sentence.

    The function ensures that each distinct sentence appears only once
    (duplicates are filtered by the caller’s ``sentence_map``).
    """
    print("Loading labels map..", flush=True)

    # Load the pickled label map
    with open(label_map_path, "rb") as f:
        label_map = pickle.load(f)

    # Extend label map with the hard‑coded LABEL_EXTENSION entries
    for ext_key, ext_label in LABEL_EXTENSION.items():
        existing = label_map.get(ext_key)
        if existing is None:
            label_map[ext_key] = [ext_label]
        else:
            if ext_label not in existing:
                existing.append(ext_label)

    # Convert requested buffer size (GB) to a safe byte count
    MAX_INT = 2_147_483_647
    buffer_bytes = max(1, min(int(buffer_gb * (1024 ** 3)), MAX_INT))

    # Optional total line count for tqdm progress bar
    total = None
    if progress:
        with open(nt_path, "r", buffering=buffer_bytes, encoding="utf-8") as cnt_f:
            total = sum(1 for _ in cnt_f)

    with open(nt_path, "r", buffering=buffer_bytes, encoding="utf-8") as f:
        iterator = tqdm(f, total=total, desc="Verbalizing") if progress else f
        for line in iterator:
            s_uri, p_uri, o_raw = _parse_nt_line(line)
            if not s_uri:
                continue

            s_labels = _extract_label(label_map, s_uri)
            p_labels = _extract_label(label_map, p_uri)

            # Object is another URI (non‑literal)
            if not _is_literal(o_raw):
                o_uri = o_raw.strip("<>")
                o_labels = _extract_label(label_map, o_uri)

                common_langs = set(s_labels) & set(p_labels) & set(o_labels)
                for lang in common_langs:
                    sentence = f"{s_labels[lang]} {p_labels[lang]} {o_labels[lang]}."
                    triple = (s_uri, p_uri, o_raw)
                    yield sentence, triple

            # Object is a literal
            else:
                lit_val, lit_lang = _strip_literal_lang(o_raw)
                lit_val = _decode_escaped(lit_val)

                # 2.1 – literal language matches subject/predicate language
                if lit_lang and lit_lang in s_labels and lit_lang in p_labels:
                    sentence = f"{s_labels[lit_lang]} {p_labels[lit_lang]} {lit_val}."
                    triple = (s_uri, p_uri, o_raw)
                    yield sentence, triple

                # 2.2 – any common language between subject and predicate
                common_sp = set(s_labels) & set(p_labels)
                for lang in common_sp:
                    if lit_lang and lang == lit_lang:
                        # already emitted in case 2.1; skip duplicate
                        continue
                    sentence = f"{s_labels[lang]} {p_labels[lang]} {lit_val}."
                    triple = (s_uri, p_uri, o_raw)
                    yield sentence, triple


def main():
    parser = argparse.ArgumentParser(
        description="Verbalize N‑Triples using label‑map generated by label_map_gen.py"
    )
    parser.add_argument(
        "nt_chunk",
        help="Path to the N‑Triples file (or chunk) to verbalize",
    )
    parser.add_argument(
        "label_map",
        help="Path to the pickle file produced by label_map_gen.py",
    )
    parser.add_argument(
        "-b",
        "--buffer-gb",
        type=float,
        default=1.0,
        help="Read buffer size in gigabytes (default 1 GB)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write verbalizations to this file (default: stdout)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable tqdm progress bar",
    )
    parser.add_argument(
        "-m",
        "--map-output",
        help=(
            "Path to store the sentence‑to‑triple pickle map. "
            "If omitted, defaults to <output>.map.pkl (or <nt_chunk>.map.pkl)."
        ),
    )
    args = parser.parse_args()

    # Ensure target directory exists (if an output file is requested)
    create_directory_if_not_exists(args.output)

    # Collect sentences and the mapping in a single pass
    sentence_map: dict[str, tuple[str, str, str]] = {}

    for sentence, triple in verbalize(
        args.nt_chunk,
        args.label_map,
        buffer_gb=args.buffer_gb,
        progress=not args.no_progress,
    ):
        # Keep only the first occurrence of a sentence (unique keys)
        sentence_map.setdefault(sentence, triple)
    
    # Once all sentences are collected as unique map keys
    out_f = (
        open(args.output, "w", encoding="utf-8", errors="replace")
        if args.output
        else sys.stdout
    )
    for sentence in sentence_map:    
        try:
            out_f.write(sentence + "\n")
        except Exception:
            print(f"Error while processing sentence: {sentence!r}", file=sys.stderr)
            raise

    if args.output:
        out_f.close()

    # Determine where to write the pickle map
    map_path = args.map_output
    if not map_path:
        base = args.output if args.output else args.nt_chunk
        map_path = f"{base}.map.pkl"

    with open(map_path, "wb") as mf:
        pickle.dump(sentence_map, mf)

    print(f"Verbalisation map written to: {map_path}", file=sys.stderr)


if __name__ == "__main__":
    main()