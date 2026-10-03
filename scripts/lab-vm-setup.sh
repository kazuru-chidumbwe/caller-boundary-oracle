#!/usr/bin/env bash
# Prepare a Debian/Ubuntu host to run the evaluation: toolchains, pinned vendors, Python venv.
# Go 1.26 must be on PATH (the distribution package is usually older; see README).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> System packages"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y -qq git curl ca-certificates openjdk-17-jdk maven python3 python3-venv \
  autoconf automake libtool pkg-config libssl-dev swig python3-dev gengetopt help2man

echo "==> Tool versions"
go version
java -version 2>&1 | head -1
mvn -version | head -1
python3 --version

echo "==> Pinned gmrtd worktrees and JMRTD"
bash "$ROOT/scripts/bootstrap-vendor.sh"
bash "$ROOT/scripts/install-jmrtd-local.sh"

echo "==> Independent chip (OpenPACE + vsmartcard)"
bash "$ROOT/scripts/bootstrap-vsmartcard.sh"

echo "==> .NET SDK and emrtd-dotnet"
bash "$ROOT/scripts/bootstrap-dotnet.sh"

echo "==> Dart SDK and dmrtd"
bash "$ROOT/scripts/bootstrap-dart.sh"

echo "==> Python venv"
make -C "$ROOT" venv

echo "Ready: make test && make smoke && make evaluate"
