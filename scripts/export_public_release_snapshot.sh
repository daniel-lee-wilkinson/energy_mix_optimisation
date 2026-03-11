#!/usr/bin/env bash
set -euo pipefail

# Export a clean snapshot (single-tree, no git history) for public publishing.
# Usage:
#   ./scripts/export_public_release_snapshot.sh [target_dir]

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

target_dir="${1:-public_release_snapshot}"

if [[ -d "$target_dir/.git" ]]; then
	echo "Refusing to overwrite '$target_dir' because it is a git repository."
	echo "Use a different output folder name, e.g.:"
	echo "  ./scripts/export_public_release_snapshot.sh public_release_export"
	exit 1
fi

rm -rf "$target_dir"
mkdir -p "$target_dir"

git archive --format=tar HEAD | tar -x -C "$target_dir"

echo "Exported tracked files to: $repo_root/$target_dir"
echo "This snapshot excludes git history and ignored local files (e.g., .env, output_data/, figures/)."
