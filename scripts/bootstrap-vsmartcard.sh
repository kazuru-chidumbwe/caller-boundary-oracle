#!/usr/bin/env bash
# Build the independent chip used for the positive control and cross-checks:
#   OpenPACE 1.1.4 (7bc871a) with Python bindings -> ../_vendor/openpace-prefix
#   vsmartcard 82bc5ad + tools/vsmartcard/vsmartcard-python3.patch -> ../_vendor/vsmartcard
# and write ../_vendor/vsmartcard.env with PYTHONPATH / LD_LIBRARY_PATH for the card script.
# Build deps (Debian): autoconf automake libtool pkg-config libssl-dev swig python3-dev gengetopt help2man
# Build deps (macOS, Homebrew): autoconf automake libtool pkg-config openssl@3 swig gengetopt help2man,
# with PKG_CONFIG_PATH pointing at openssl@3
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/../_vendor}"
mkdir -p "$VENDOR_DIR"
VENDOR_DIR="$(cd "$VENDOR_DIR" && pwd)"
OPENPACE_COMMIT=7bc871ab0063c6f1e2443a9b7168262bbe8fa8be
VSMARTCARD_COMMIT=82bc5ad066b26ee057d2af200c1a66e3a65a9743
PYCRYPTODOMEX_VERSION=3.23.0
PREFIX="$VENDOR_DIR/openpace-prefix"
PYVER="$(python3 -c "import sys; print(f'python{sys.version_info.major}.{sys.version_info.minor}')")"
SITE="$PREFIX/local/lib/$PYVER/dist-packages"

if [[ ! -d "$VENDOR_DIR/openpace/.git" ]]; then
  git clone -q https://github.com/frankmorgner/openpace.git "$VENDOR_DIR/openpace"
fi
if [[ "$(cat "$PREFIX/.commit" 2>/dev/null)" != "$OPENPACE_COMMIT" ]]; then
  echo "==> build OpenPACE ${OPENPACE_COMMIT:0:7}"
  (
    cd "$VENDOR_DIR/openpace"
    git fetch -q origin && git checkout -q "$OPENPACE_COMMIT"
    autoreconf --install > /dev/null 2>&1
    ./configure --prefix="$PREFIX" --enable-python > /dev/null
    make -j"$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN)" > /dev/null
    # setuptools only installs the bindings into a directory that is on PYTHONPATH.
    mkdir -p "$SITE"
    PYTHONPATH="$SITE" make install > /dev/null
  )
  echo "$OPENPACE_COMMIT" > "$PREFIX/.commit"
fi

if [[ ! -d "$VENDOR_DIR/vsmartcard/.git" ]]; then
  git clone -q https://github.com/frankmorgner/vsmartcard.git "$VENDOR_DIR/vsmartcard"
fi
(
  cd "$VENDOR_DIR/vsmartcard"
  git fetch -q origin
  git checkout -q -f "$VSMARTCARD_COMMIT"
  git apply "$ROOT/tools/vsmartcard/vsmartcard-python3.patch"
)

EGG="$( (compgen -G "$PREFIX/local/lib/python3*/dist-packages/OpenPACE-*.egg" \
  || compgen -G "$PREFIX/lib/python3*/site-packages/OpenPACE-*.egg" || true) | head -n 1)"
if [[ -z "$EGG" ]]; then
  echo "bootstrap-vsmartcard: OpenPACE Python bindings not found under $PREFIX" >&2
  exit 1
fi
# vsmartcard's DES/3DES (BAC secure messaging) comes from PyCryptodome; PACE runs in OpenPACE.
PYDEPS="$VENDOR_DIR/vsmartcard-pydeps"
if [[ ! -d "$PYDEPS/Cryptodome" ]]; then
  python3 -m pip install -q --target "$PYDEPS" "pycryptodomex==$PYCRYPTODOMEX_VERSION"
fi
cat > "$VENDOR_DIR/vsmartcard.env" <<ENV
export PYTHONPATH="$EGG:$VENDOR_DIR/vsmartcard/virtualsmartcard/src/vpicc:$PYDEPS\${PYTHONPATH:+:\$PYTHONPATH}"
export LD_LIBRARY_PATH="$PREFIX/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export DYLD_LIBRARY_PATH="$PREFIX/lib\${DYLD_LIBRARY_PATH:+:\$DYLD_LIBRARY_PATH}"
ENV
# shellcheck source=/dev/null
source "$VENDOR_DIR/vsmartcard.env"
python3 -c "import eac; from virtualsmartcard.cards import nPA; from Cryptodome.Cipher import DES3"
echo "vsmartcard ready: OpenPACE ${OPENPACE_COMMIT:0:7}, vsmartcard ${VSMARTCARD_COMMIT:0:7} (+patch); env in $VENDOR_DIR/vsmartcard.env"
