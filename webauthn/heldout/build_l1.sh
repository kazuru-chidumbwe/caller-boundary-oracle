#!/usr/bin/env bash
# L1: build the unchanged WebAuthn drivers against the newest releases (16 Nov 2026), the same way as
# build_releases.sh builds the held-out releases. Expectations for these arms are in expectations.json
# (write_expectations.py, DERIVED), committed before the run. A release whose API the driver cannot call
# fails here and is recorded as not built. Writes webauthn/heldout/drivers-l1.json (new arms only) and
# build-status-l1.tsv.
#
# Usage: VENDOR_DIR=... webauthn/heldout/build_l1.sh
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/../_vendor}"
H="$ROOT/webauthn/heldout"
B="$H/build-l1"
mkdir -p "$B"
status="$H/build-status-l1.tsv"
printf 'arm\trelease\tbuilt\tnote\n' > "$status"
declare -A CMD
ok() { printf '%s\t%s\tyes\t%s\n' "$1" "$2" "${3:-}" >> "$status"; }
no() { printf '%s\t%s\tno\t%s\n' "$1" "$2" "$3" >> "$status"; }

v=14.1.0; d="$B/simplewebauthn-$v"; rm -rf "$d"; mkdir -p "$d"
cp "$ROOT/webauthn/drivers/node/simplewebauthn_driver.js" "$d/"
if (cd "$d" && PATH="$VENDOR_DIR/node/bin:$PATH" npm init -y > /dev/null && \
    PATH="$VENDOR_DIR/node/bin:$PATH" npm install --no-audit --no-fund --ignore-scripts --save-exact "@simplewebauthn/server@$v" > "$d.log" 2>&1); then
  ok simplewebauthn "$v"; CMD["simplewebauthn@$v"]="$VENDOR_DIR/node/bin/node $d/simplewebauthn_driver.js"
else no simplewebauthn "$v" "npm install failed"; fi

java_build() {  # arm release keep-class artifact
  local arm="$1" v="$2" keep="$3" art="$4" d="$B/java-$1-$2"
  rm -rf "$d"; cp -r "$ROOT/webauthn/drivers/java" "$d"; rm -rf "$d/target"
  find "$d/src/main/java" -name '*Driver.java' ! -name "$keep.java" -delete
  perl -0pi -e "s|(<artifactId>$art</artifactId>\s*<version>)[^<]*|\${1}$v|" "$d/pom.xml"
  [ "$art" = webauthn-server-core ] && perl -0pi -e "s|(<artifactId>yubico-util</artifactId><version>)[^<]*|\${1}$v|" "$d/pom.xml"
  if (cd "$d" && mvn -q -B package -DskipTests > "$d.log" 2>&1); then
    echo "$d/target/webauthn-drivers-1.0.0.jar:$d/target/lib/*"
  else
    return 1
  fi
}
yv=2.10.1
if cp=$(java_build java-webauthn-server "$yv" YubicoDriver webauthn-server-core); then
  ok java-webauthn-server "$yv"; CMD["java-webauthn-server@$yv"]="java -cp $cp org.callerboundary.webauthn.YubicoDriver"
else no java-webauthn-server "$yv" "maven build failed (see $B/java-java-webauthn-server-$yv.log)"; fi
wv=0.32.0.RELEASE
if cp=$(java_build webauthn4j "$wv" Webauthn4jDriver webauthn4j-core); then
  ok webauthn4j "$wv"
  CMD["webauthn4j-nonstrict@$wv"]="java -cp $cp org.callerboundary.webauthn.Webauthn4jDriver nonstrict"
  CMD["webauthn4j-strict@$wv"]="java -cp $cp org.callerboundary.webauthn.Webauthn4jDriver strict"
else no webauthn4j "$wv" "maven build failed (see $B/java-webauthn4j-$wv.log)"; fi

# shellcheck disable=SC1091
source "$VENDOR_DIR/dotnet.env"
for v in 4.3.3 5.0.0-preview.10; do
  d="$B/fido2-$v"; rm -rf "$d"; mkdir -p "$d"
  cp "$ROOT/webauthn/drivers/dotnet/Program.cs" "$ROOT/webauthn/drivers/dotnet/Fido2Driver.csproj" "$d/"
  sed -i "s|Include=\"Fido2\" Version=\"[^\"]*\"|Include=\"Fido2\" Version=\"$v\"|" "$d/Fido2Driver.csproj"
  if (cd "$d" && dotnet build -c Release -o out --nologo -v q > "$d.log" 2>&1); then
    ok fido2-net-lib "$v"; CMD["fido2-net-lib@$v"]="$VENDOR_DIR/dotnet/dotnet $d/out/Fido2Driver.dll"
  else no fido2-net-lib "$v" "$(grep -m1 -o 'error [A-Z]*[0-9]*: [^[]*' "$d.log" || tail -1 "$d.log")"; fi
done

python3 - "$H/drivers-l1.json" <<'PY' "${!CMD[@]}" -- "${CMD[@]}"
import json, sys
out = sys.argv[1]
rest = sys.argv[2:]
i = rest.index("--")
json.dump(dict(zip(rest[:i], rest[i + 1:])), open(out, "w"), indent=1)
print(i, "arms built")
PY
cat "$status"
