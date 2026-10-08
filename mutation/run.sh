#!/usr/bin/env bash
# Run the mutation baseline with the same toolchain environment as the evaluation suites.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then PATH="$ROOT/.venv/bin:$PATH"; fi
if [[ -d /usr/local/go/bin ]]; then PATH="/usr/local/go/bin:$PATH"; fi
export GOTOOLCHAIN="${GOTOOLCHAIN:-local}"
for env_file in "$ROOT/../_vendor/vsmartcard.env" "$ROOT/../_vendor/dotnet.env" "$ROOT/../_vendor/dart.env"; do
  # shellcheck source=/dev/null
  if [[ -f "$env_file" ]]; then source "$env_file"; fi
done
exec python3 mutation/run_mutants.py "$@"
