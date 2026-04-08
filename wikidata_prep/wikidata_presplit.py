#!/usr/bin/env python3
"""
wikidata_presplit.py — Phase 1: Split a large .nt.gz into chunks of a specific size,
cutting ONLY at entity boundaries so each chunk is self-contained.
Usage:
    python wikidata_presplit.py latest-all.nt.gz --chunk-size 10 --outdir chunks/
Produces:  chunks/chunk_0000.nt.zst, chunks/chunk_0001.nt.zst ...
"""
import argparse
import gzip
import os
import sys
import subprocess
import shutil
try:
    from tqdm import tqdm
except ImportError:
    print("WARNING: tqdm not installed — no progress bar.", file=sys.stderr)
    tqdm = None

WD_ENTITY_PREFIX = b"<http://www.wikidata.org/entity/"
MAX_ENTITY_SIZE = 100 * 1024 * 1024  # 100 MB safety limit per entity

def owning_entity_bytes(line: bytes) -> bytes | None:
    if not line.startswith(WD_ENTITY_PREFIX):
        return None
    rest = line[len(WD_ENTITY_PREFIX):]
    if rest.startswith(b"statement/"):
        rest = rest[len(b"statement/"):]
    end = 0
    while end < len(rest) and rest[end:end + 1] not in (b">", b"-", b"/", b" "):
        end += 1
    qid = rest[:end]
    if qid.startswith(b"Q") and qid[1:].isdigit():
        return qid
    return None

def estimate_uncompressed_size(path: str) -> int | None:
    """Still useful for the progress bar."""
    try:
        disk_size = os.path.getsize(path)
    except OSError:
        return None
    if path.endswith(".gz"): return disk_size * 20
    elif path.endswith(".bz2"): return disk_size * 6
    elif path.endswith(".zst"):
        try:
            r = subprocess.run(["zstd", "-l", "--no-progress", path], capture_output=True, text=True, timeout=10)
            for line in r.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[0].endswith(".zst"): return int(parts[2])
        except Exception: pass
        return disk_size * 3
    return disk_size

def presplit(input_path: str, chunk_size_gb: float, outdir: str, use_zstd: bool = True):
    os.makedirs(outdir, exist_ok=True)
    ext = ".nt.zst" if use_zstd else ".nt"
    
    # Calculate target bytes directly from GB input
    target_bytes_per_chunk = int(chunk_size_gb * 1024**3)
    print(f"Target size per chunk: {chunk_size_gb} GB ({target_bytes_per_chunk:,} bytes)", file=sys.stderr)

    if input_path.endswith(".gz"):
        cmd = ["pigz", "-dc", input_path] if shutil.which("pigz") else ["zcat", input_path]
        infile = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**7).stdout
    elif input_path.endswith(".bz2"):
        import bz2
        infile = bz2.open(input_path, "rb")
    elif input_path.endswith(".zst"):
        infile = subprocess.Popen(["zstd", "-d", "--stdout", "--no-progress", input_path], stdout=subprocess.PIPE).stdout
    else:
        infile = open(input_path, "rb")

    est_total = estimate_uncompressed_size(input_path)
    pbar = None
    if tqdm is not None:
        pbar = tqdm(total=est_total, unit="B", unit_scale=True, unit_divisor=1024, desc="Pre-split")

    chunk_idx = 0
    current_entity: bytes | None = None
    bytes_in_chunk = 0
    entity_buffer: list[bytes] = []
    total_lines = 0
    total_entities = 0

    def open_chunk(idx):
        path = os.path.join(outdir, f"chunk_{idx:05d}{ext}") # Increased to 05d for very large datasets
        if use_zstd:
            proc = subprocess.Popen(["zstd", "-T0", "-3", "--no-progress", "-o", path], stdin=subprocess.PIPE)
            return proc.stdin, proc
        else:
            return open(path, "wb"), None

    out, proc = open_chunk(chunk_idx)

    def flush_buffer():
        nonlocal bytes_in_chunk
        if not entity_buffer: return
        data_to_write = b''.join(entity_buffer)
        out.write(data_to_write)
        bytes_in_chunk += len(data_to_write)
        entity_buffer.clear()

    entity_buffer_size = 0
    for raw_line in infile:
        total_lines += 1
        line_len = len(raw_line)
        if pbar is not None: pbar.update(line_len)
            
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(b"#"):
            entity_buffer.append(raw_line)
            entity_buffer_size += line_len
            continue
            
        entity = owning_entity_bytes(stripped)
        
        if entity_buffer_size > MAX_ENTITY_SIZE:
            flush_buffer()
            entity_buffer_size = 0

        if entity is not None and entity != current_entity:
            flush_buffer()
            entity_buffer_size = 0
            total_entities += 1
            
            if pbar is not None and total_entities % 100_000 == 0:
                pbar.set_postfix(chunk=f"{chunk_idx + 1}", entities=f"{total_entities:,}", refresh=False)
                
            # REMOVED: 'and chunk_idx < num_chunks - 1'
            # Now it just checks if the current chunk has reached the size limit
            if bytes_in_chunk >= target_bytes_per_chunk:
                out.close()
                if proc: proc.wait()
                chunk_idx += 1
                bytes_in_chunk = 0
                out, proc = open_chunk(chunk_idx)
                
            current_entity = entity
            
        entity_buffer.append(raw_line)
        entity_buffer_size += line_len

    flush_buffer()
    out.close()
    if proc: proc.wait()
    infile.close()
    if pbar: pbar.close()

    print(f"\nDone: {total_lines:,} lines, {total_entities:,} entities -> {chunk_idx + 1} chunks in {outdir}/", file=sys.stderr)

def main():
    p = argparse.ArgumentParser(description="Pre-split Wikidata NT dump into chunks of fixed size.")
    p.add_argument("input", help="Input .nt / .nt.gz / .nt.bz2 / .nt.zst file")
    p.add_argument("--chunk-size", type=float, default=10.0, help="Target size per chunk in GB (default: 10.0)")
    p.add_argument("--outdir", default="chunks", help="Output directory (default: chunks/)")
    p.add_argument("--no-zstd", action="store_true", help="Write plain .nt instead of .nt.zst")
    args = p.parse_args()
    presplit(args.input, args.chunk_size, args.outdir, use_zstd=not args.no_zstd)

if __name__ == "__main__":
    main()