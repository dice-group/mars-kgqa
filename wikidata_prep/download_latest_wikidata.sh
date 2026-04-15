#!/bin/sh
#SBATCH --job-name=wikidata_download
#SBATCH --output=wikidata_download_%j.out   # STDOUT
#SBATCH --error=wikidata_download_%j.err    # STDERR
#SBATCH --time=24:00:00                     # Wall‑clock limit
#SBATCH --mem=4G                            # Memory per node
#SBATCH --cpus-per-task=1                   # CPU cores
#SBATCH --partition=normal

set -eu
#
# ------------------------------------------------------------
# SLURM batch script – download the latest Wikidata dump
# with automatic resume, retry logic and a date‑stamped filename.
#
# The output file will be named like:
#     latest-all_21012026.nt.gz
# (DDMMYYYY = day‑month‑year when the script is run)
#
# Usage:
#   sbatch download_latest_wikidata.sh
#
# ------------------------------------------------------------


# ------------------------------------------------------------
# Configuration (edit if needed)
# ------------------------------------------------------------
URL="https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.nt.gz"

# Insert today’s date in the format DDMMYYYY
DATE=$(date +%d%m%Y)

# Build the filename:
#   original base   : latest-all.nt.gz
#   date‑stamped    : latest-all_21012026.nt.gz
BASE_NAME="${URL##*/}"               # latest-all.nt.gz
NAME_NO_EXT="${BASE_NAME%.gz}"        # latest-all.nt
FILE="${NAME_NO_EXT}_${DATE}.gz"      # latest-all_21012026.nt.gz

MAX_RETRIES=5                         # How many retry attempts
RETRY_DELAY=30                        # Seconds to wait between attempts
# ------------------------------------------------------------

# -------------------------
# Helper: timestamp logger
# -------------------------
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# -------------------------
# Choose a downloader
# -------------------------
if command -v wget >/dev/null 2>&1; then
    DOWNLOADER="wget"
elif command -v curl >/dev/null 2>&1; then
    DOWNLOADER="curl"
else
    log "ERROR: Neither wget nor curl is installed on this node."
    exit 1
fi

log "Downloader   : $DOWNLOADER"
log "Target URL   : $URL"
log "Output file  : $FILE"

# ------------------------------------------------------------
# Single download attempt (returns 0 on success)
# ------------------------------------------------------------
download_once() {
    if [[ "$DOWNLOADER" == "wget" ]]; then
        # -c  : continue / resume
        wget -c --quiet -O "$FILE" "$URL"
    else
        # -C - : continue / resume
        curl -C - -L -s -o "$FILE" "$URL"
    fi
}

# ------------------------------------------------------------
# Retry loop
# ------------------------------------------------------------
attempt=1
while (( attempt <= MAX_RETRIES )); do
    log "Attempt $attempt of $MAX_RETRIES..."

    if download_once; then
        log "Download completed successfully."
        exit 0
    else
        log "Download failed (exit code $?)."
        ((attempt++))
        if (( attempt <= MAX_RETRIES )); then
            log "Waiting $RETRY_DELAY seconds before next attempt..."
            sleep $RETRY_DELAY
        else
            log "Maximum retries reached – exiting with error."
            exit 1
        fi
    fi
done