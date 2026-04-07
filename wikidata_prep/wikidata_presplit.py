#!/usr/bin/env python3
"""
wikidata_presplit.py — Phase 1: Split a large .nt.gz into N chunk files,
cutting ONLY at entity boundaries so each chunk is self-contained.

Usage:
    python wikidata_presplit.py latest-all.nt.gz --chunks 200 --outdir chunks/

Produces:  chunks/chunk_0000.nt.zst  …  chunks/chunk_0199.nt.zst
(Uses zstd for ~3x faster compression/decompression than gzip.)

Requirements:
    pip install tqdm
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
    print(
        "WARNING: tqdm not installed — no progress bar. "
        "Install with: pip install tqdm",
        file=sys.stderr,
    )
    tqdm = None

WD_ENTITY_PREFIX = b"<http://www.wikidata.org/entity/"
MAX_ENTITY_SIZE = 100 * 1024 * 1024  # 100 MB safety limit per entity


def owning_entity_bytes(line: bytes) -> bytes | None:
    """Extract the owning entity QID from a raw NT line (bytes)."""
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
    """Estimate uncompressed byte count for progress bar total."""
    try:
        disk_size = os.path.getsize(path)
    except OSError:
        return None

    if path.endswith(".gz"):
        return disk_size * 5
    elif path.endswith(".bz2"):
        return disk_size * 6
    elif path.endswith(".zst"):
        try:
            r = subprocess.run(
                ["zstd", "-l", "--no-progress", path],
                capture_output=True, text=True, timeout=10,
            )
            for line in r.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[0].endswith(".zst"):
                    return int(parts[2])
        except Exception:
            pass
        return disk_size * 3
    else:
        return disk_size


def presplit(input_path: str, num_chunks: int, outdir: str, use_zstd: bool = True):
    os.makedirs(outdir, exist_ok=True)
    ext = ".nt.zst" if use_zstd else ".nt"

    # Open input
    # if input_path.endswith(".gz"):
    #     infile = gzip.open(input_path, "rb")
    if input_path.endswith(".gz"):
        # Use pigz if available, otherwise zcat
        cmd = ["pigz", "-dc", input_path] if shutil.which("pigz") else ["zcat", input_path]
        infile = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**7)
        infile = infile.stdout 
    elif input_path.endswith(".bz2"):
        import bz2
        infile = bz2.open(input_path, "rb")
    elif input_path.endswith(".zst"):
        infile = subprocess.Popen(
            ["zstd", "-d", "--stdout", "--no-progress", input_path],
            stdout=subprocess.PIPE,
        ).stdout
    else:
        infile = open(input_path, "rb")

    est_total = estimate_uncompressed_size(input_path)

    if est_total:
        target_bytes_per_chunk = est_total // num_chunks
    else:
        target_bytes_per_chunk = 3_000_000_000_000 // num_chunks

    print(f"Target bytes per chunk: ~{target_bytes_per_chunk / 1e9:.1f} GB", file=sys.stderr)

    # ── Progress bar ──
    pbar = None
    if tqdm is not None:
        pbar = tqdm(
            total=est_total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc="Pre-split",
            miniters=1,
            smoothing=0.05,
        )

    chunk_idx = 0
    current_entity: bytes | None = None
    bytes_in_chunk = 0
    entity_buffer: list[bytes] = []
    total_lines = 0
    total_entities = 0

    def open_chunk(idx):
        path = os.path.join(outdir, f"chunk_{idx:04d}{ext}")
        if use_zstd:
            proc = subprocess.Popen(
                ["zstd", "-T0", "-3", "--no-progress", "-o", path],
                stdin=subprocess.PIPE,
            )
            return proc.stdin, proc
        else:
            return open(path, "wb"), None

    out, proc = open_chunk(chunk_idx)

    def flush_buffer():
        nonlocal bytes_in_chunk
        if not entity_buffer:
            return
        
        # Join all lines into one large byte-string 
        # This reduces thousands of system calls to just one.
        data_to_write = b''.join(entity_buffer)
        out.write(data_to_write)
        
        bytes_in_chunk += len(data_to_write)
        entity_buffer.clear()

    entity_buffer_size = 0  # Track size of current entity in bytes

    for raw_line in infile:
        total_lines += 1
        line_len = len(raw_line)
        
        if pbar is not None:
            pbar.update(line_len)
            
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(b"#"):
            entity_buffer.append(raw_line)
            entity_buffer_size += line_len
            continue
            
        entity = owning_entity_bytes(stripped)
        
        # FIX #3: Mega-Entity Safety Check
        # If the current entity is taking up too much RAM, flush it now
        if entity_buffer_size > MAX_ENTITY_SIZE:
            flush_buffer()
            entity_buffer_size = 0 # Reset size after flush

        if entity is not None and entity != current_entity:
            flush_buffer()
            entity_buffer_size = 0 # Reset size after flush
            total_entities += 1
            
            if pbar is not None and total_entities % 100_000 == 0:
                pbar.set_postfix(
                    chunk=f"{chunk_idx + 1}/{num_chunks}",
                    entities=f"{total_entities:,}",
                    refresh=False,
                )
                
            if bytes_in_chunk >= target_bytes_per_chunk and chunk_idx < num_chunks - 1:
                out.close()
                if proc:
                    proc.wait()
                chunk_idx += 1
                bytes_in_chunk = 0
                out, proc = open_chunk(chunk_idx)
                
            current_entity = entity
            
        entity_buffer.append(raw_line)
        entity_buffer_size += line_len

    flush_buffer()
    out.close()
    if proc:
        proc.wait()
    infile.close()

    if pbar is not None:
        pbar.set_postfix(
            chunk=f"{chunk_idx + 1}/{num_chunks}",
            entities=f"{total_entities:,}",
        )
        pbar.close()

    print(
        f"\nDone: {total_lines:,} lines, {total_entities:,} entities "
        f"-> {chunk_idx + 1} chunks in {outdir}/",
        file=sys.stderr,
    )


def main():
    p = argparse.ArgumentParser(
        description="Pre-split Wikidata NT dump into chunks at entity boundaries."
    )
    p.add_argument("input", help="Input .nt / .nt.gz / .nt.bz2 / .nt.zst file")
    p.add_argument("--chunks", type=int, default=200,
                    help="Number of chunks (default: 200)")
    p.add_argument("--outdir", default="chunks",
                    help="Output directory (default: chunks/)")
    p.add_argument("--no-zstd", action="store_true",
                    help="Write plain .nt instead of .nt.zst")
    args = p.parse_args()
    presplit(args.input, args.chunks, args.outdir, use_zstd=not args.no_zstd)


if __name__ == "__main__":
    main()
