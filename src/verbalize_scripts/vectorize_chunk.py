# For a given chunk file, read lines in batches and send them to the embedding function
# Make sure that each entry has a vector, embedding model throws exception replace it empty list
# Write the embeddings in lines to another file in output directory, named similar to the input file
from src.util.llm import get_embeddings
from src.const.llm import DEFAULT_EMBED_LLM_CONFIG
import os
import json
from tqdm import tqdm

def vectorize_chunk_file(input_path: str, output_dir: str, batch_size: int = 32) -> None:
    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Build output file path – keep the original name and add a suffix
    base_name = os.path.basename(input_path)
    out_path = os.path.join(output_dir, f"{base_name}.embeddings")

    with open(input_path, "r", encoding="utf-8") as inp, \
         open(out_path, "w", encoding="utf-8") as out:
        batch = []
        line_refs = []  # retain original lines for matching results

        for line in inp:
            line = line.rstrip("\n")
            if not line:
                # Preserve empty lines with an empty embedding
                _write_line(out, [])
                continue

            batch.append(line)
            line_refs.append(line)

            # When we hit the batch size, embed and write results
            if len(batch) == batch_size:
                _process_batch(batch, line_refs, out)
                batch.clear()
                line_refs.clear()

        # Process any remaining lines not forming a full batch
        if batch:
            _process_batch(batch, line_refs, out)


def _process_batch(batch: list[str], originals: list[str], out_f) -> None:
    try:
        embeddings = get_embeddings(batch, DEFAULT_EMBED_LLM_CONFIG)
        # ``get_embeddings`` should return a list of vectors matching ``batch`` order
        if not isinstance(embeddings, list) or len(embeddings) != len(batch):
            raise ValueError("Unexpected embedding response shape")
    except Exception as exc:
        # If the whole batch fails, fall back to empty embeddings for each line
        embeddings = [[] for _ in batch]

    # Write each line with its (possibly empty) embedding
    for original, vector in zip(originals, embeddings):
        # Guard against per‑item failures that might be embedded as None
        if not isinstance(vector, list):
            vector = []
        _write_line(out_f, vector)


def _write_line(out_f, embedding):
    out_f.write(str(embedding) + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Read a chunk file, embed each line in batches, and write embeddings to an output file."
    )
    parser.add_argument(
        "input_path",
        help="Path to the chunk file to be vectorized."
    )
    parser.add_argument(
        "output_dir",
        help="Directory where the .embeddings file will be created."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1024,
        help="Number of lines to process per embedding request (default: 32)."
    )

    args = parser.parse_args()

    vectorize_chunk_file(
        input_path=args.input_path,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
    )