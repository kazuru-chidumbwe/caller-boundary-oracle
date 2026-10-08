#!/usr/bin/env bash
# T63: run the D5 leading-zero check in every gmrtd release of the version sweep, plus a fixed control.
#
# For each tag the release source is exported from the gmrtd clone (git archive), the test file is copied
# into its chipauth package, and only that test runs (go test -run TestT63). The release itself is not
# modified otherwise. Control: v1.3.2 with the drafted fix (fix-control.patch) applied must report
# D5_ABSENT; v1.3.2 unchanged must report D5_PRESENT.
#
# Usage: analysis/t63/run.sh GMRTD_CLONE OUT_DIR
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
clone="$1"; out="$2"
mkdir -p "$out"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
tags="$(git -C "$clone" tag | grep -E '^v(0\.(4[0-9])|1\.)' | sort -V)"
result="$out/t63.tsv"
printf 'release\tcommit\tgo_test\tverdict\tdetail\n' > "$result"

run_one() {  # name dir
  local name="$1" dir="$2" log="$out/$1.log" line rc=0
  cp "$here/zz_t63_leading_zero_test.go" "$dir/chipauth/"
  (cd "$dir" && GOFLAGS=-mod=mod go test ./chipauth -run TestT63 -count=1 -v) > "$log" 2>&1 || rc=$?
  line="$(grep -m1 '^T63 ' "$log" || true)"
  if [ -n "$line" ]; then
    printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$3" "rc=$rc" "$(sed 's/.*verdict=//' <<< "$line")" "$line" >> "$result"
  else
    printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$3" "rc=$rc" "NOT_RUN" "$(tail -1 "$log" | tr '\t' ' ')" >> "$result"
  fi
}

for t in $tags; do
  d="$work/$t"; mkdir -p "$d"
  git -C "$clone" archive "$t" | tar -x -C "$d"
  run_one "$t" "$d" "$(git -C "$clone" rev-parse --short "$t^{commit}")"
done

d="$work/v1.3.2-fixed"; mkdir -p "$d"
git -C "$clone" archive v1.3.2 | tar -x -C "$d"
(cd "$d" && patch -p1 -s < "$here/fix-control.patch")
run_one "v1.3.2+fix-control" "$d" "$(git -C "$clone" rev-parse --short 'v1.3.2^{commit}')+patch"

go version > "$out/go-version.txt"
cat "$result"
