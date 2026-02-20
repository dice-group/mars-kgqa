import argparse
import json
import os
import sys
from collections import defaultdict
import codecs
from tqdm import tqdm

## Sample usage:  bash pylauncher.sh normal src.verbalize_scripts.label_map_gen data_dir/verbalization/rdf_labels.nt -o data_dir/verbalization/label_map.pkl -b 80
## Slurm: sbatch -N 1 -n 1 -c 4 -t 01:00:00 -o data_dir/verbalization/logs/%j_label_map_gen.log  --partition normal --mem 200G 

# Last run 18.02.2026: 0:25:34 : Building mapping: 100%|██████████| 510188728/510188728 [20:52<00:00, 407366.10it/s] 

LANG_FILTER = {'en', 'de', 'fr', 'ba', 'be', 'es', 'hy', 'ru', 'uk', 'zh'}

def _decode_escaped(label: str) -> str:
    """
    Convert escaped Unicode sequences (e.g., '\\u00D6') into real characters.
    If the string contains a stray back‑slash that breaks the Unicode‑escape
    decoder, we fall back to a tolerant decode that ignores the problem.
    """
    try:
        # Normal case – everything is well‑formed.
        return codecs.decode(label, "unicode_escape")
    except UnicodeDecodeError:
        # Fallback: treat the string as bytes and decode with 'ignore' for errors.
        # This keeps all valid \\uXXXX sequences and leaves any lone '\' as is.
        return label.encode("utf-8", errors="ignore").decode(
            "unicode_escape", errors="ignore"
        )


def _parse_line(line: str):
    """
    Parse a single N‑Triples line of the form:
        <subject> <predicate> "label"@lang .
    Returns (subject_uri, label_with_lang) or (None, None) on failure.
    """
    # Trim whitespace and split only on the first two spaces.
    parts = line.strip().split(" ", 2)
    if len(parts) < 3:
        return None, None

    # Subject: strip surrounding angle brackets.
    subject = parts[0].strip("<>")

    # Object part contains the literal and possibly language/datatype tags.
    obj = parts[2].rsplit(" .", 1)[0]  # remove trailing space+dot

    # Extract the literal value (everything between the first pair of quotes).
    if obj.startswith('"'):
        # Find the closing quote that matches the opening one.
        end_quote = obj.find('"', 1)
        if end_quote == -1:
            return subject, None
        raw_label = obj[1:end_quote]               # still escaped (e.g. BLK\\u00D6)
        # Decode escaped Unicode safely.
        label = _decode_escaped(raw_label)

        # Grab any language tag that follows the closing quote (e.g., @en).
        remainder = obj[end_quote + 1 :].strip()
        if remainder.startswith("@"):
            lang = remainder[1:].split()[0]  # take up to next whitespace
            if lang not in LANG_FILTER:
                return None, None
            label = f"{label}@{lang}"
        # (If a datatype (^^) appears we ignore it; only language is kept.)
    else:
        label = obj  # fallback – unlikely for proper N‑Triples

    return subject, label

def _calc_buffer_bytes(gb: float) -> int:
    """Convert GB to bytes and clamp to a safe range for open()."""
    # 2 147 483 647 is the max positive 32‑bit signed int (C int on most builds)
    MAX_INT = 2_147_483_647
    raw = int(gb * (1024 ** 3))
    # Ensure we never pass 0 (which means unbuffered) and never exceed C int.
    return max(1, min(raw, MAX_INT))

def _uri_last_part(uri: str) -> str:
    """
    Return the terminal component of a URI, i.e. the substring after the
    last '/' or '#'.  If neither separator is present, return the original
    string.
    """
    if not uri:
        return uri
    # Find the last separator.
    sep_index = max(uri.rfind("/"), uri.rfind("#"))
    return uri[sep_index + 1 :] if sep_index != -1 else uri

def build_mapping(input_path: str, buffer_bytes: int) -> dict:
    """
    Stream‑read *input_path* using *buffer_bytes* and return a dict:
    {uri_last_part: [label@lang, …]}.
    """
    mapping = defaultdict(list)

    # First pass: count total lines for tqdm total
    print('Counting entries..')
    with open(input_path, "r", buffering=buffer_bytes, encoding="utf-8") as count_f:
        total_lines = sum(1 for _ in count_f)

    # Second pass: process with progress bar
    with open(input_path, "r", buffering=buffer_bytes, encoding="utf-8") as f:
        for line in tqdm(f, total=total_lines, desc="Building mapping"):
            if not line.strip():
                continue
            subj, label = _parse_line(line)
            if subj and label:
                # Use only the last part of the URI as the dictionary key.
                key = _uri_last_part(subj)
                mapping[key].append(label)

    return dict(mapping)  # cast to plain dict for serialization

def main():
    parser = argparse.ArgumentParser(
        description="Create subject‑label mapping from rdf_labels.nt"
    )
    parser.add_argument(
        "input",
        help="Path to the rdf_labels.nt file produced by label_grep.sh",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write a pickle file instead of JSON (default: stdout JSON)",
        default=None,
    )
    parser.add_argument(
        "-b",
        "--buffer-gb",
        type=float,
        default=1.0,
        metavar="GB",
        help="Read buffer size in gigabytes (default: 1 GB). "
             "Must be a positive number; the script converts it to bytes.",
    )

    args = parser.parse_args()

    # Convert GB to bytes for the built‑in buffering argument.
    buffer_bytes = _calc_buffer_bytes(args.buffer_gb)

    mapping = build_mapping(args.input, buffer_bytes)
    print('Writing output..')
    if args.output:
        import pickle
        with open(args.output, "wb") as out_f:
            pickle.dump(mapping, out_f, protocol=pickle.HIGHEST_PROTOCOL)
    else:
        json.dump(mapping, sys.stdout, ensure_ascii=False, indent=None)
    print('Process complete.')

if __name__ == "__main__":
    main()