#!/usr/bin/env bash
# Install and build the WebAuthn arm (fault peer and six relying-party library drivers):
#   Python venv with webauthn/requirements.txt (hash-pinned; py_webauthn 3.0.1) -> ../_vendor/webauthn-venv
#   Node.js 24.21.0 (checksum verified) -> ../_vendor/node; @simplewebauthn/server 14.0.3 from package-lock.json
#   go-webauthn v0.18.2 (go.sum) -> bin/webauthn-go-driver
#   java-webauthn-server 2.10.0 and webauthn4j-core 0.31.11.RELEASE (Maven) -> webauthn/drivers/java/target
#   Fido2 4.2.0 (NuGet, packages.lock.json) -> webauthn/drivers/dotnet/out (needs bootstrap-dotnet.sh first)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/../_vendor}"
mkdir -p "$VENDOR_DIR"
VENDOR_DIR="$(cd "$VENDOR_DIR" && pwd)"
NODE_VERSION=24.21.0
NODE_SHA256=fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6

echo "==> Python fault peer and py_webauthn"
if [[ ! -x "$VENDOR_DIR/webauthn-venv/bin/python" ]]; then
  python3 -m venv "$VENDOR_DIR/webauthn-venv"
fi
"$VENDOR_DIR/webauthn-venv/bin/pip" install -q --require-hashes -r "$ROOT/webauthn/requirements.txt"

if [[ "$("$VENDOR_DIR/node/bin/node" --version 2>/dev/null)" != "v$NODE_VERSION" ]]; then
  echo "==> install Node.js $NODE_VERSION"
  tarball="$VENDOR_DIR/node.tar.xz"
  curl -sSL -o "$tarball" "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-x64.tar.xz"
  echo "$NODE_SHA256  $tarball" | sha256sum -c - > /dev/null
  rm -rf "$VENDOR_DIR/node" "$VENDOR_DIR/node-v$NODE_VERSION-linux-x64"
  tar -xJf "$tarball" -C "$VENDOR_DIR"
  mv "$VENDOR_DIR/node-v$NODE_VERSION-linux-x64" "$VENDOR_DIR/node"
  rm "$tarball"
fi
echo "==> @simplewebauthn/server"
(cd "$ROOT/webauthn/drivers/node" && PATH="$VENDOR_DIR/node/bin:$PATH" npm ci --no-audit --no-fund --ignore-scripts --silent)

echo "==> go-webauthn"
(cd "$ROOT/webauthn/drivers/go" && GOFLAGS=-mod=readonly go build -trimpath -o "$ROOT/bin/webauthn-go-driver" .)

echo "==> java-webauthn-server and webauthn4j"
(cd "$ROOT/webauthn/drivers/java" && mvn -q -B package -DskipTests)

echo "==> Fido2"
# shellcheck disable=SC1091
source "$VENDOR_DIR/dotnet.env"
(cd "$ROOT/webauthn/drivers/dotnet" && dotnet build -c Release -p:RestoreLockedMode=true -o out --nologo -v q > /dev/null)

echo "webauthn ready: python, node $NODE_VERSION, go, java and .NET drivers built"
