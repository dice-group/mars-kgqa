
import argparse
import os
import shlex
import subprocess
from pathlib import Path
from typing import List
from src.util.common import create_directory_if_not_exists

## Sample usage: bash pylauncher.sh normal src.verbalize_scripts.set_chunk_verbalize_jobs --chunk_root_dir /scratch/hpc-prf-merlin/project_data/wikidata_qald10_dump/2000_chunks --log_dir data_dir/verbalization/logs --data_dir data_dir/verbalization --output_script launch_chunks_verbalization.sh 

# For a given directory with file chunks, spawn a slurm job for each file found in it
# Slurm command: sbatch -N 1 -n 1 -c 2 -t 02:00:00 -o {log_dir}/{chunk_dir_name}/%j_{chunk_file_name}.log --partition normal --mem 80G pylauncher.sh normal src.verbalize_scripts.verbalize_nt_chunk {chunk_root_dir}/{chunk_dir_name}/{chunk_file_name}.{chunk_file_extension} data_dir/verbalization/label_map.pkl -o data_dir/verbalization/{chunk_dir_name}/{chunk_file_name}.txt

def _is_chunk_file(p: Path) -> bool:
    """Return ``True`` if *p* looks like a chunk file (has a name + extension)."""
    return p.is_file() and p.suffix  # any file with an extension qualifies


def _build_sbatch_command(
    *,
    log_dir: Path,
    chunk_root_dir: Path,
    chunk_dir: Path,
    chunk_file: Path,
    data_dir: Path,
    begin_offset_seconds: int = 0,
) -> List[str]:
    """
    Construct the SBATCH command (as a list suitable for ``subprocess``).
    """
    # Relative path components for readability in the log / output filenames
    # ``rel_chunk_dir`` is the path *inside* the chunk root (e.g. "" if files are
    # stored directly under the root).  We also prepend the root‑directory name
    # so logs and outputs are grouped under a folder like ``2000_chunks``.
    rel_chunk_dir = chunk_dir.relative_to(chunk_root_dir).as_posix()
    root_name = chunk_root_dir.name
    # If ``rel_chunk_dir`` is empty we just use the root name; otherwise we join
    # root name with the relative sub‑path.
    chunk_subpath = Path(root_name) / rel_chunk_dir if rel_chunk_dir else Path(root_name)

    chunk_name = chunk_file.stem               # file name without extension
    chunk_ext = chunk_file.suffix.lstrip(".")  # extension without leading dot

    # Log file pattern: <log_dir>/<root_name>/<relative_dir>/%j_<chunk_name>.log
    log_path = log_dir / chunk_subpath / f"%j_{chunk_name}.log"
    
    create_directory_if_not_exists(log_path)

    # Output file for the verbalization result
    out_path = data_dir / chunk_subpath / f"{chunk_name}.txt"
    
    create_directory_if_not_exists(out_path)

    # Build the command (list of arguments)
    cmd = [
        "sbatch",
        "-N", "1",
        "-n", "1",
        "-c", "2",
        "-t", "02:00:00",
        "-o", str(log_path),
        "--partition", "normal",
        "--mem", "80G",
        *(["--begin", f"now+{begin_offset_seconds}"] if begin_offset_seconds else []),
        "pylauncher.sh",
        "normal",
        "src.verbalize_scripts.verbalize_nt_chunk",
        str(chunk_file),                                    # input chunk
        str(data_dir / "label_map.pkl"), # label map (fixed)
        "-o", str(out_path),                               # output file (fixed)
    ]
    return cmd


def _gather_chunk_files(chunk_root_dir: Path) -> List[Path]:
    """Yield every chunk file under *chunk_root_dir* (recursively)."""
    files = []
    for root, _, filenames in os.walk(chunk_root_dir):
        for fn in filenames:
            p = Path(root) / fn
            if _is_chunk_file(p):
                files.append(p)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create and optionally submit SLURM jobs for each chunk file."
    )
    parser.add_argument(
        "--chunk_root_dir",
        type=Path,
        required=True,
        help="Root directory containing sub‑directories of chunk files.",
    )
    parser.add_argument(
        "--log_dir",
        type=Path,
        required=True,
        help="Base directory where SLURM job logs will be stored.",
    )
    parser.add_argument(
        "--data_dir",
        type=Path,
        required=True,
        help="Directory containing the verbalization data (label map & output).",
    )
    parser.add_argument(
        "--output_script",
        type=Path,
        default=None,
        help="If supplied, write all SBATCH commands to this file (executable).",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Print commands instead of executing/submitting them.",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Immediately submit each generated command via subprocess.run()."
    )
    args = parser.parse_args()

    # Ensure directories exist
    for d in (args.chunk_root_dir, args.log_dir, args.data_dir):
        if not d.is_dir():
            raise FileNotFoundError(f"Required directory does not exist: {d}")

    chunk_files = _gather_chunk_files(args.chunk_root_dir)

    if not chunk_files:
        print("No chunk files found – nothing to do.")
        return

    # Prepare output script if requested
    script_fh = None
    if args.output_script:
        args.output_script.parent.mkdir(parents=True, exist_ok=True)
        script_fh = open(args.output_script, "w", encoding="utf-8")
        script_fh.write("#!/usr/bin/env bash\n\n")

    job_counter = 0

    for chunk_path in chunk_files:
        chunk_dir = chunk_path.parent

        # Compute delay: after each block of 10 jobs, add 30 s per block
        delay_seconds = (job_counter // 100) * 120   # 0 for first 10, 30 for next 10, ...

        cmd_list = _build_sbatch_command(
            log_dir=args.log_dir,
            chunk_root_dir=args.chunk_root_dir,
            chunk_dir=chunk_dir,
            chunk_file=chunk_path,
            data_dir=args.data_dir,
            begin_offset_seconds=delay_seconds,
        )
        # Render the command as a shell‑safe string for printing / script writing
        cmd_str = " ".join(shlex.quote(tok) for tok in cmd_list)

        if args.dry_run:
            print(cmd_str)

        if script_fh:
            script_fh.write(f"{cmd_str}\n")

        if args.submit and not args.dry_run:
            # Directly invoke sbatch; capture output for debugging
            result = subprocess.run(cmd_list, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Failed to submit {chunk_path.name}:\n{result.stderr}")
            else:
                print(f"Submitted {chunk_path.name}: {result.stdout.strip()}")
        
        job_counter += 1

    if script_fh:
        script_fh.close()
        # Make the script executable
        os.chmod(args.output_script, 0o755)
        print(f"All commands written to {args.output_script}")

if __name__ == "__main__":
    main()