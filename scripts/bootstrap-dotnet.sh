#!/usr/bin/env bash
# Install the pinned .NET SDK and emrtd-dotnet next to the harness:
#   .NET SDK 10.0.401 -> ../_vendor/dotnet   (dotnet-install.sh, no system packages)
#   emrtd-dotnet 0433b3a -> ../_vendor/emrtd-dotnet
# and write ../_vendor/dotnet.env, which puts that SDK first on PATH.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/../_vendor}"
mkdir -p "$VENDOR_DIR"
VENDOR_DIR="$(cd "$VENDOR_DIR" && pwd)"
DOTNET_SDK=10.0.401
EMRTD_DOTNET_COMMIT=0433b3a7608d55d806d992397451e6962d17f3c7

if [[ "$("$VENDOR_DIR/dotnet/dotnet" --version 2>/dev/null)" != "$DOTNET_SDK" ]]; then
  echo "==> install .NET SDK $DOTNET_SDK"
  curl -sSL -o "$VENDOR_DIR/dotnet-install.sh" https://dot.net/v1/dotnet-install.sh
  bash "$VENDOR_DIR/dotnet-install.sh" --version "$DOTNET_SDK" --install-dir "$VENDOR_DIR/dotnet" --no-path > /dev/null
fi

if [[ ! -d "$VENDOR_DIR/emrtd-dotnet/.git" ]]; then
  git clone -q https://github.com/chamnan/emrtd-dotnet.git "$VENDOR_DIR/emrtd-dotnet"
fi
git -C "$VENDOR_DIR/emrtd-dotnet" fetch -q origin
git -C "$VENDOR_DIR/emrtd-dotnet" checkout -q --detach "$EMRTD_DOTNET_COMMIT"

cat > "$VENDOR_DIR/dotnet.env" <<ENV
export PATH="$VENDOR_DIR/dotnet:\$PATH"
export DOTNET_ROOT="$VENDOR_DIR/dotnet"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1
ENV
echo "dotnet ready: SDK $("$VENDOR_DIR/dotnet/dotnet" --version), emrtd-dotnet ${EMRTD_DOTNET_COMMIT:0:7}; env in $VENDOR_DIR/dotnet.env"
