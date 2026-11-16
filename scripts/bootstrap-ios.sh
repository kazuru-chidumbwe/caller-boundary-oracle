#!/usr/bin/env bash
# macOS only. Pinned NFCPassportReader checkout with the test-visibility patch, next to the harness:
#   NFCPassportReader 6e37f1a (2.3.3, default) -> ../_vendor/NFCPassportReader
# NFCPR_VERSION=3.0.0 (8e1758e) or 3.0.1 (e52a401) selects a later release and its own patch; 3.0.1's patch
# also adds an internal mrzKey setter for the access key that release introduced.
# The patch only turns eight private stored properties of PassportReader into internal ones, so
# the test can set the read options and call PassportReader.startReading without an NFC session.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/../_vendor}"
mkdir -p "$VENDOR_DIR"
VENDOR_DIR="$(cd "$VENDOR_DIR" && pwd)"
case "${NFCPR_VERSION:-2.3.3}" in
  2.3.3) COMMIT=6e37f1ab249fef82771da46d32707f2b94ed090f; PATCH=nfcpassportreader-test-visibility.patch ;;
  3.0.0) COMMIT=8e1758eb23db64ecc90f237be791521d7999e07c; PATCH=nfcpassportreader-test-visibility-3.0.0.patch ;;
  3.0.1) COMMIT=e52a401e3651c2e898adcc31e3e059e224813bcc; PATCH=nfcpassportreader-test-visibility-3.0.1.patch ;;
  *) echo "unknown NFCPR_VERSION ${NFCPR_VERSION}" >&2; exit 1 ;;
esac

if [[ ! -d "$VENDOR_DIR/NFCPassportReader/.git" ]]; then
  git clone -q https://github.com/AndyQ/NFCPassportReader.git "$VENDOR_DIR/NFCPassportReader"
fi
cd "$VENDOR_DIR/NFCPassportReader"
git fetch -q origin
git checkout -q -f --detach "$COMMIT"
git apply "$ROOT/drivers/ios/$PATCH"
echo "NFCPassportReader ${NFCPR_VERSION:-2.3.3} ${COMMIT:0:7} ready (+ $PATCH)"
