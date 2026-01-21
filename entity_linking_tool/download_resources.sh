#!/bin/bash
set -eu

ZENODO_URL="https://zenodo.org/records/18326537/files/el_resources.tar.gz?download=1"

TARGET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_ARCHIVE="${TARGET_DIR}/resource_bundle.tar.gz"
# download the resources tar.gz and extract it here

# Download the archive
echo "Downloading resources from Zenodo..."
if command -v curl >/dev/null 2>&1; then
    curl -L -o "${TMP_ARCHIVE}" "${ZENODO_URL}"
elif command -v wget >/dev/null 2>&1; then
    wget -O "${TMP_ARCHIVE}" "${ZENODO_URL}"
else
    echo "Error: Neither curl nor wget is installed." >&2
    exit 1
fi

echo "Download complete: ${TMP_ARCHIVE}"

# Extract the archive – strip the top‑level folder
echo "Extracting archive into ${TARGET_DIR} (removing top‑level folder)..."
mkdir -p "${TARGET_DIR}"
tar -xzf "${TMP_ARCHIVE}" -C "${TARGET_DIR}" --strip-components=1

echo "Extraction finished."

# Clean up
rm -f "${TMP_ARCHIVE}"
echo "Temporary file removed."