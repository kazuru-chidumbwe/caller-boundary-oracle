#!/usr/bin/env bash
# macOS only. Pinned NFCPassportReader checkout with the test-visibility patch, next to the harness:
#   NFCPassportReader 6e37f1a -> ../_vendor/NFCPassportReader
# The patch only turns eight private stored properties of PassportReader into internal ones, so
# the test can set the read options and call PassportReader.startReading without an NFC session.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/../_vendor}"
mkdir -p "$VENDOR_DIR"
VENDOR_DIR="$(cd "$VENDOR_DIR" && pwd)"
COMMIT=6e37f1ab249fef82771da46d32707f2b94ed090f

if [[ ! -d "$VENDOR_DIR/NFCPassportReader/.git" ]]; then
  git clone -q https://github.com/AndyQ/NFCPassportReader.git "$VENDOR_DIR/NFCPassportReader"
fi
cd "$VENDOR_DIR/NFCPassportReader"
git fetch -q origin
git checkout -q -f --detach "$COMMIT"
git apply "$ROOT/drivers/ios/nfcpassportreader-test-visibility.patch"
echo "NFCPassportReader ${COMMIT:0:7} ready (+ test-visibility patch)"
