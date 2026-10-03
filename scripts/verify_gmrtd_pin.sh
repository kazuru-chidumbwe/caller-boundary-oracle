#!/usr/bin/env bash
# Fail if any gmrtd worktree is not at its pinned commit.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/../_vendor}"
# shellcheck source=/dev/null
source "$ROOT/scripts/gmrtd-pin.sh"
for commit in "${GMRTD_PINS[@]}"; do
  dir="$(gmrtd_dir "$commit")"
  if [[ ! -d "$dir" ]]; then
    echo "verify_gmrtd_pin: missing $dir; run bash scripts/bootstrap-vendor.sh" >&2
    exit 1
  fi
  actual="$(git -C "$dir" rev-parse HEAD)"
  if [[ "$actual" != "$commit" ]]; then
    echo "verify_gmrtd_pin: $dir is at $actual, want $commit" >&2
    exit 1
  fi
done
echo "gmrtd pins OK: ${GMRTD_PINS[*]}" | sed -E 's/([0-9a-f]{7})[0-9a-f]{33}/\1/g'
