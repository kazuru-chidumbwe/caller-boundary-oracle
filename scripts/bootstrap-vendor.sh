#!/usr/bin/env bash
# Check out every pinned gmrtd commit as a sibling worktree (../_vendor/gmrtd-<short>) and
# build the drivers against each. go.mod is never rewritten here: a pin/go.mod mismatch
# fails the build instead of silently dirtying the tree.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/../_vendor}"
# shellcheck source=/dev/null
source "$ROOT/scripts/gmrtd-pin.sh"

mkdir -p "$VENDOR_DIR"
if [[ ! -d "$VENDOR_DIR/gmrtd/.git" ]]; then
  echo "==> clone gmrtd"
  git clone -q "$GMRTD_REPO_URL" "$VENDOR_DIR/gmrtd"
fi

for commit in "${GMRTD_PINS[@]}"; do
  dir="$(gmrtd_dir "$commit")"
  git -C "$VENDOR_DIR/gmrtd" fetch -q origin "$commit" 2>/dev/null || git -C "$VENDOR_DIR/gmrtd" fetch -q origin
  if [[ ! -d "$dir" ]]; then
    git -C "$VENDOR_DIR/gmrtd" worktree add -q --detach "$dir" "$commit"
  fi
  git -C "$dir" checkout -q --detach "$commit"
  echo "  gmrtd $(git -C "$dir" rev-parse --short HEAD) -> $dir"
done

export GOTOOLCHAIN="${GOTOOLCHAIN:-local}"
cd "$ROOT"
go build ./...
go build -modfile=gomod/gmrtd-8fea245.mod -tags gmrtd_8fea245 ./...
go build -modfile=gomod/gmrtd-b861835.mod -tags gmrtd_b861835 ./...
echo "go build OK at every pin (go.mod unchanged)"
