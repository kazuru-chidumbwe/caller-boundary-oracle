#!/usr/bin/env bash
# passauf sources for the Rust driver, pinned by commit:
#   v0.2.0 48b7cc7 -> ../_vendor/passauf          (drivers/rust, the scored release)
#   v0.2.1 05098d8 -> ../_vendor/passauf-v0.2.1   (drivers/rust-v0.2.1, the release with the D8 and D9 fixes)
# Requires network and git. The driver itself is built by classifier/run_suite.py with cargo (Rust 1.92.0 used).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/../_vendor}"
REPO="${PASSAUF_REPO_URL:-https://github.com/aveao/passauf}"
mkdir -p "$VENDOR_DIR"

pin() {  # dir commit
  local dir="$1" commit="$2"
  if [[ ! -d "$dir/.git" ]]; then
    git clone -q "$REPO" "$dir"
  fi
  git -C "$dir" fetch -q origin --tags || true
  git -C "$dir" checkout -q --detach "$commit"
  [[ "$(git -C "$dir" rev-parse HEAD)" == "$commit" ]] || { echo "passauf: $dir is not at $commit" >&2; exit 2; }
  echo "  passauf $(git -C "$dir" describe --tags 2>/dev/null || git -C "$dir" rev-parse --short HEAD) -> $dir"
}

pin "$VENDOR_DIR/passauf" 48b7cc7d7398bbdfdcfef2c900a01972275c6c8a
pin "$VENDOR_DIR/passauf-v0.2.1" 05098d8a629cf6122492166146aa7a8bda4b49ba
