#!/usr/bin/env bash
set -euo pipefail

# Simple guardrail checks before publishing this repository publicly.

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

failed=0

echo "Running public-release anonymity checks..."

# 1) No tracked local environment files.
if git ls-files -- '.env' '*.env' | grep -q .; then
  echo "[FAIL] Tracked env files detected (.env / *.env)."
  git ls-files -- '.env' '*.env'
  failed=1
else
  echo "[PASS] No tracked .env files."
fi

# 2) No tracked generated artifacts under ignored folders.
if git ls-files output_data figures | grep -q .; then
  echo "[FAIL] Tracked generated artifacts detected in output_data/ or figures/."
  git ls-files output_data figures
  failed=1
else
  echo "[PASS] No tracked files in output_data/ or figures/."
fi

# 3) No known site-specific legacy labels.
if git --no-pager grep -n -i -E 'moomba' -- ':!scripts/check_public_release_safety.sh' >/tmp/privacy_check_hits.txt; then
  echo "[FAIL] Found site-identifying label(s) in tracked files:"
  cat /tmp/privacy_check_hits.txt
  failed=1
else
  echo "[PASS] No legacy site labels found in tracked files."
fi
rm -f /tmp/privacy_check_hits.txt

# 4) No old hardcoded coordinate defaults from prior versions.
if git --no-pager grep -n -E '(-28\.1083|140\.2028|-29\.0139|134\.7544)' -- . >/tmp/privacy_check_coords.txt; then
  echo "[FAIL] Found legacy hardcoded coordinate defaults in tracked files:"
  cat /tmp/privacy_check_coords.txt
  failed=1
else
  echo "[PASS] No legacy hardcoded coordinate defaults found."
fi
rm -f /tmp/privacy_check_coords.txt

# 5) History warning (current tree may be clean while history is not).
history_site_hits="$(git --no-pager log --all --oneline -S'moomba' || true)"
if [[ -n "$history_site_hits" ]]; then
  echo "[WARN] Git history contains legacy site-label references."
  echo "       Use ./scripts/export_public_release_snapshot.sh for a history-free public release."
fi

if [[ "$failed" -ne 0 ]]; then
  echo ""
  echo "Public-release anonymity checks failed. Resolve the items above before publishing."
  exit 1
fi

echo ""
echo "All public-release anonymity checks passed."
