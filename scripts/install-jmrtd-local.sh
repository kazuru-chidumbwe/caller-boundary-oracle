#!/usr/bin/env bash
# Fetch the pinned JMRTD release from Maven Central and check its SHA-256. Requires network + Maven.
set -euo pipefail

VERSION="${JMRTD_VERSION:-0.8.9}"
# Override JMRTD_JAR_SHA256 only together with JMRTD_VERSION for an intentional version bump.
EXPECTED_SHA256="${JMRTD_JAR_SHA256:-89959D0C8CB8CF7B93699B18D135675A7B8760489BDDD924EE3174C447FA5409}"

echo "==> Resolving org.jmrtd:jmrtd:${VERSION} from Maven Central"
mvn -q dependency:get -Dartifact="org.jmrtd:jmrtd:${VERSION}"

JAR="$HOME/.m2/repository/org/jmrtd/jmrtd/${VERSION}/jmrtd-${VERSION}.jar"
if [[ ! -f "$JAR" ]]; then
  echo "error: jar not found at $JAR" >&2
  exit 2
fi

# SHA-256 check (Linux sha256sum or macOS/Windows-compatible python)
ACTUAL="$(python3 - <<PY
import hashlib, pathlib
p = pathlib.Path(r"""$JAR""")
print(hashlib.sha256(p.read_bytes()).hexdigest().upper())
PY
)"
if [[ "$ACTUAL" != "$EXPECTED_SHA256" ]]; then
  echo "error: JMRTD ${VERSION} jar SHA-256 mismatch" >&2
  echo "  expected $EXPECTED_SHA256" >&2
  echo "  actual   $ACTUAL" >&2
  exit 3
fi

echo "Installed $JAR"
echo "SHA-256 OK ($ACTUAL)"
