#!/usr/bin/env bash
# Build the unchanged WebAuthn drivers against the held-out releases (HELD-OUT-DESIGN.md, release rule).
# Each release gets its own build directory under webauthn/heldout/build/; nothing in the pinned build
# changes. A release whose API the driver cannot call fails here and is recorded as not built.
# Writes webauthn/heldout/drivers-heldout.json (pinned and held-out arms) and build-status.tsv.
#
# Usage: VENDOR_DIR=... webauthn/heldout/build_releases.sh
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/../_vendor}"
H="$ROOT/webauthn/heldout"
B="$H/build"
mkdir -p "$B"
status="$H/build-status.tsv"
printf 'arm\trelease\tbuilt\tnote\n' > "$status"
declare -A CMD
ok() { printf '%s\t%s\tyes\t%s\n' "$1" "$2" "${3:-}" >> "$status"; }
no() { printf '%s\t%s\tno\t%s\n' "$1" "$2" "$3" >> "$status"; }

# py_webauthn 2.8.0: own venv, same requirements except the library
v=2.8.0; d="$B/py_webauthn-$v"
if python3 -m venv "$d/venv" && "$d/venv/bin/pip" install -q "webauthn==$v" cbor2 cryptography > "$d.log" 2>&1; then
  ok py_webauthn "$v"; CMD["py_webauthn@$v"]="$d/venv/bin/python $ROOT/webauthn/drivers/py_webauthn_driver.py"
else no py_webauthn "$v" "pip install failed (see $d.log)"; fi

# simplewebauthn 13.3.3: copy of the driver with its own node_modules
v=13.3.3; d="$B/simplewebauthn-$v"; mkdir -p "$d"
cp "$ROOT/webauthn/drivers/node/simplewebauthn_driver.js" "$d/"
if (cd "$d" && PATH="$VENDOR_DIR/node/bin:$PATH" npm init -y > /dev/null && \
    PATH="$VENDOR_DIR/node/bin:$PATH" npm install --no-audit --no-fund --ignore-scripts --save-exact "@simplewebauthn/server@$v" > "$d.log" 2>&1); then
  ok simplewebauthn "$v"; CMD["simplewebauthn@$v"]="$VENDOR_DIR/node/bin/node $d/simplewebauthn_driver.js"
else no simplewebauthn "$v" "npm install failed"; fi

# go-webauthn v0.17.4: copy of the driver module, library version replaced
v=v0.17.4; d="$B/go-webauthn-$v"; mkdir -p "$d"
cp "$ROOT/webauthn/drivers/go/main.go" "$ROOT/webauthn/drivers/go/go.mod" "$d/"
if (cd "$d" && go mod edit -require="github.com/go-webauthn/webauthn@$v" && go mod tidy > "$d.log" 2>&1 && \
    go build -trimpath -o "$d/driver" . >> "$d.log" 2>&1); then
  ok go-webauthn "$v"; CMD["go-webauthn@$v"]="$d/driver"
else no go-webauthn "$v" "$(tail -1 "$d.log")"; fi

# java-webauthn-server 1.12.4 and webauthn4j 0.30.3.RELEASE: built separately, each from a copy of the Java
# drivers that holds only its own driver class and the changed library version
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
yv=1.12.4
if cp=$(java_build java-webauthn-server "$yv" YubicoDriver webauthn-server-core); then
  ok java-webauthn-server "$yv"; CMD["java-webauthn-server@$yv"]="java -cp $cp org.callerboundary.webauthn.YubicoDriver"
else no java-webauthn-server "$yv" "$(grep -m1 -A1 'cannot find symbol' "$B/java-java-webauthn-server-$yv.log" | tail -1 | sed 's/^\[ERROR\] *//')"; fi
wv=0.30.3.RELEASE
if cp=$(java_build webauthn4j "$wv" Webauthn4jDriver webauthn4j-core); then
  ok webauthn4j "$wv"
  CMD["webauthn4j-nonstrict@$wv"]="java -cp $cp org.callerboundary.webauthn.Webauthn4jDriver nonstrict"
  CMD["webauthn4j-strict@$wv"]="java -cp $cp org.callerboundary.webauthn.Webauthn4jDriver strict"
else no webauthn4j "$wv" "maven build failed (see $B/java-webauthn4j-$wv.log)"; fi

# Fido2 3.0.1 and 5.0.0-preview.7: copies of the .NET driver, package version changed, lock file regenerated
# shellcheck disable=SC1091
source "$VENDOR_DIR/dotnet.env"
for v in 3.0.1 5.0.0-preview.7; do
  d="$B/fido2-$v"; rm -rf "$d"; mkdir -p "$d"
  cp "$ROOT/webauthn/drivers/dotnet/Program.cs" "$ROOT/webauthn/drivers/dotnet/Fido2Driver.csproj" "$d/"
  sed -i "s|Include=\"Fido2\" Version=\"[^\"]*\"|Include=\"Fido2\" Version=\"$v\"|" "$d/Fido2Driver.csproj"
  if (cd "$d" && dotnet build -c Release -o out --nologo -v q > "$d.log" 2>&1); then
    ok fido2-net-lib "$v"; CMD["fido2-net-lib@$v"]="$VENDOR_DIR/dotnet/dotnet $d/out/Fido2Driver.dll"
  else no fido2-net-lib "$v" "$(grep -m1 -o 'error [A-Z]*[0-9]*: [^[]*' "$d.log" || tail -1 "$d.log")"; fi
done

# drivers file: the pinned arms (from drivers.json) plus every held-out arm that built
python3 - "$ROOT" "$VENDOR_DIR" "$H/drivers-heldout.json" <<'PY' "${!CMD[@]}" -- "${CMD[@]}"
import json, sys
root, vendor, out = sys.argv[1:4]
rest = sys.argv[4:]
i = rest.index("--")
keys, vals = rest[:i], rest[i + 1:]
pinned = json.load(open(f"{root}/webauthn/drivers.json"))
d = {k: v.replace("{ROOT}", root).replace("{VENDOR}", vendor) for k, v in pinned.items()}
d.update(dict(zip(keys, vals)))
json.dump(d, open(out, "w"), indent=1)
print(len(d), "arms")
PY
cat "$status"
