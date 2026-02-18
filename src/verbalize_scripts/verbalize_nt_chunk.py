import argparse
import pickle
import sys
from tqdm import tqdm
from src.verbalize_scripts.label_map_gen import _decode_escaped, _uri_last_part
from src.util.common import create_directory_if_not_exists

## Sample usage: bash pylauncher.sh normal src.verbalize_scripts.verbalize_nt_chunk /scratch/hpc-prf-merlin/project_data/wikidata_qald10_dump/2000_chunks/dataset_chunk_0926.nt data_dir/verbalization/label_map.pkl -o data_dir/verbalization/2000_chunks/dataset_chunk_0926.txt

LABEL_EXTENSION = {'description': 'description@en'} # Accomodate http://schema.org/description

# TODO: Store the triples alongside the verbalizations, mapping the verbalized string to the triple tuple, store the map as a pickle file
# TODO: Output the verbalization (unique keys) from the map as line separated string to a txt file in the end

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
    # label_map was built with only the last part of the URI as the key.
    key = _uri_last_part(uri)
    raw = label_map.get(key, [])
    result = {}
    for entry in raw:
        # entry may already contain "@lang"
        if "@" in entry:
            txt, lang = entry.rsplit("@", 1)
            result[lang] = txt
        else:
            # fallback – treat as language‑agnostic
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
    # Find closing quote that terminates the literal value.
    end = lit.rfind('"')
    value = lit[1:end]
    rest = lit[end + 1 :].strip()
    lang = ""
    if rest.startswith("@"):
        lang = rest[1:].split()[0]
    return value, lang


# Core verbalization logic
def verbalize(
    nt_path: str,
    label_map_path: str,
    buffer_gb: float = 1.0,
    progress: bool = True,
):
    """Yield verbalized sentences for each eligible triple."""
    print('Loading labels map..', flush=True)
    # Load label map (pickled dict)
    with open(label_map_path, "rb") as f:
        label_map = pickle.load(f)
        # extend label map with LABEL_EXTENSION
        for ext_key, ext_label in LABEL_EXTENSION.items():
            existing = label_map.get(ext_key)
            if existing is None:
                label_map[ext_key] = [ext_label]
            else:
                if ext_label not in existing:
                    existing.append(ext_label)

    # Convert buffer size to bytes (same helper as label_map_gen)
    MAX_INT = 2_147_483_647
    buffer_bytes = max(1, min(int(buffer_gb * (1024 ** 3)), MAX_INT))

    # First pass to know total lines for tqdm (optional)
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

            # Retrieve label dictionaries for subject & predicate
            s_labels = _extract_label(label_map, s_uri)
            p_labels = _extract_label(label_map, p_uri)

            # Case 1: object is a URI (non‑literal), need its label too
            if not _is_literal(o_raw):
                o_uri = o_raw.strip("<>")
                o_labels = _extract_label(label_map, o_uri)

                # Need all three languages to intersect
                common_langs = set(s_labels) & set(p_labels) & set(o_labels)
                for lang in common_langs:
                    s_lab = s_labels[lang]
                    p_lab = p_labels[lang]
                    o_lab = o_labels[lang]
                    yield f"{s_lab} {p_lab} {o_lab}."

            else:
                # Object is a literal, we only need subject & predicate
                lit_val, lit_lang = _strip_literal_lang(o_raw)
                lit_val = _decode_escaped(lit_val)

                # Two sub‑cases:
                # 2.1: s, p, and literal share the same language tag
                # 2.2: s and p share a language, literal language is ignored
                # We respect the explicit language when present.
                # Sub‑case 2.1 – match literal language if it exists
                if lit_lang:
                    if lit_lang in s_labels and lit_lang in p_labels:
                        yield f"{s_labels[lit_lang]} {p_labels[lit_lang]} {lit_val}."
                    # else fall back to sub‑case 2.2
                # Sub‑case 2.2 – any common language between s and p
                common_sp = set(s_labels) & set(p_labels)
                for lang in common_sp:
                    # avoid double‑emitting the same sentence if we already emitted
                    # it in 2.1 (i.e., when lit_lang == lang)
                    if lit_lang and lang == lit_lang:
                        continue
                    yield f"{s_labels[lang]} {p_labels[lang]} {lit_val}."


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
    args = parser.parse_args()
    
    create_directory_if_not_exists(args.output)

    out_f = open(args.output, "w", encoding="utf-8", errors="replace") if args.output else sys.stdout

    for sentence in verbalize(
        args.nt_chunk,
        args.label_map,
        buffer_gb=args.buffer_gb,
        progress=not args.no_progress,
    ):
        try:
            out_f.write(sentence + "\n")
        except Exception as e:
            # Print the problematic sentence to stderr and re‑raise
            import sys
            print(f"Error while processing sentence: {sentence!r}", file=sys.stderr)
            raise  # Preserve the original traceback

    if args.output:
        out_f.close()


if __name__ == "__main__":
    main()