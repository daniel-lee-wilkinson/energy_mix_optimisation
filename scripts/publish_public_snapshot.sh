#!/bin/bash
# scripts/publish_public_snapshot.sh
# Safely publish anonymized files to public_release_snapshot and run privacy checks

set -euo pipefail

SRC_DIR="$(dirname "$0")/.."
SNAPSHOT_DIR="$SRC_DIR/public_release_snapshot"
PRIVACY_GUARD="$SRC_DIR/scripts/check_public_release_safety.sh"

# List of files/folders to copy (edit as needed)
INCLUDE_LIST=(
    README.md
    report.md
    requirements_20250420_111430.txt
    run_lp_optimization.py
    run_optimization.py
    src/
    figures/
    output_data/
)

# 1. Run privacy guard
if ! bash "$PRIVACY_GUARD"; then
    echo "[ERROR] Privacy guard failed. Aborting publish."
    exit 1
fi

# 2. Refuse to overwrite a git repo
if [ -d "$SNAPSHOT_DIR/.git" ]; then
    echo "[ERROR] Refusing to overwrite '$SNAPSHOT_DIR' because it is a git repository."
    exit 1
fi

# 3. Clean snapshot dir
rm -rf "$SNAPSHOT_DIR"
mkdir -p "$SNAPSHOT_DIR"

# 4. Copy only approved files/folders
for item in "${INCLUDE_LIST[@]}"; do
    if [ -e "$SRC_DIR/$item" ]; then
        cp -a "$SRC_DIR/$item" "$SNAPSHOT_DIR/"
    fi
done

# 5. Success message
cat <<EOF
[INFO] Public snapshot updated at '$SNAPSHOT_DIR'.
Review and commit/push changes from that directory as needed.
EOF
