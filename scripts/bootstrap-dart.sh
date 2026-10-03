#!/usr/bin/env bash
# Install the pinned Dart SDK and dmrtd next to the harness:
#   Dart SDK 3.13.5 -> ../_vendor/dart-sdk (checksum verified)
#   dmrtd 3b6c091   -> ../_vendor/dmrtd
#   tripledes_nullsafety 1.0.3 -> ../_vendor/tripledes_nullsafety
# tripledes_nullsafety (dmrtd's 3DES dependency) declares a Flutter SDK dependency but its
# code never imports Flutter; the copy here drops that one pubspec line so plain Dart can
# resolve dmrtd. No code is changed. Writes ../_vendor/dart.env (Dart first on PATH).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/../_vendor}"
mkdir -p "$VENDOR_DIR"
VENDOR_DIR="$(cd "$VENDOR_DIR" && pwd)"
DART_VERSION=3.13.5
DART_SHA256=ea864bc64df30a6b8bdf30b2e32550f7717d9a890de8f40293aeabb924fe232b
DMRTD_COMMIT=3b6c091843573b275ae68a87335e1872f8b60ea0
TRIPLEDES_SHA256=39589b5271e96f2abc592f046e14c3dbcd87bd140c1e6f10f4005e6fb0c28b68

if [[ "$("$VENDOR_DIR/dart-sdk/bin/dart" --version 2>&1 | awk '{print $4}')" != "$DART_VERSION" ]]; then
  echo "==> install Dart SDK $DART_VERSION"
  zip="$VENDOR_DIR/dartsdk.zip"
  curl -sSL -o "$zip" "https://storage.googleapis.com/dart-archive/channels/stable/release/$DART_VERSION/sdk/dartsdk-linux-x64-release.zip"
  echo "$DART_SHA256  $zip" | sha256sum -c - > /dev/null
  rm -rf "$VENDOR_DIR/dart-sdk"
  unzip -q "$zip" -d "$VENDOR_DIR"
  rm "$zip"
fi

if [[ ! -d "$VENDOR_DIR/dmrtd/.git" ]]; then
  git clone -q https://github.com/ZeroPass/dmrtd.git "$VENDOR_DIR/dmrtd"
fi
git -C "$VENDOR_DIR/dmrtd" fetch -q origin
git -C "$VENDOR_DIR/dmrtd" checkout -q --detach "$DMRTD_COMMIT"

if [[ ! -f "$VENDOR_DIR/tripledes_nullsafety/pubspec.yaml" ]]; then
  echo "==> tripledes_nullsafety 1.0.3"
  tgz="$VENDOR_DIR/tripledes_nullsafety.tar.gz"
  curl -sSL -o "$tgz" https://pub.dev/api/archives/tripledes_nullsafety-1.0.3.tar.gz
  echo "$TRIPLEDES_SHA256  $tgz" | sha256sum -c - > /dev/null
  rm -rf "$VENDOR_DIR/tripledes_nullsafety"
  mkdir -p "$VENDOR_DIR/tripledes_nullsafety"
  tar -xzf "$tgz" -C "$VENDOR_DIR/tripledes_nullsafety"
  rm "$tgz"
  python3 - "$VENDOR_DIR/tripledes_nullsafety/pubspec.yaml" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
text, n = re.subn(r"\n  flutter:\n    sdk: flutter", "", text, count=1)
assert n == 1, "unexpected tripledes_nullsafety pubspec layout"
open(path, "w", encoding="utf-8").write(text)
PY
fi
if grep -rqE "import ['\"]package:flutter" "$VENDOR_DIR/tripledes_nullsafety/lib"; then
  echo "bootstrap-dart: tripledes_nullsafety imports Flutter; the pubspec edit is not safe" >&2
  exit 1
fi

# The driver stubs flutter_nfc_kit, expandable and diffie_hellman (drivers/dart/stubs). That is
# only sound while dmrtd imports flutter_nfc_kit solely from its NFC provider and the other two
# not at all.
lib="$VENDOR_DIR/dmrtd/lib"
if grep -rlE "package:(expandable|diffie_hellman)/" "$lib" | grep -q .; then
  echo "bootstrap-dart: dmrtd now imports expandable or diffie_hellman; revisit drivers/dart/stubs" >&2
  exit 1
fi
if [[ "$(grep -rlE "package:flutter_nfc_kit/" "$lib")" != "$lib/src/com/nfc_provider.dart" ]]; then
  echo "bootstrap-dart: dmrtd imports flutter_nfc_kit outside its NFC provider; revisit drivers/dart/stubs" >&2
  exit 1
fi

cat > "$VENDOR_DIR/dart.env" <<ENV
export PATH="$VENDOR_DIR/dart-sdk/bin:\$PATH"
ENV
echo "dart ready: SDK $DART_VERSION, dmrtd ${DMRTD_COMMIT:0:7}; env in $VENDOR_DIR/dart.env"
