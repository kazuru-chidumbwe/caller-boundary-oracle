#!/usr/bin/env python3
"""Manifest-driven suite runner — produces reproducible per-run artifacts + summary."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "classifier"))
from constants import SUITE_N_DEFAULT  # noqa: E402
from provenance import tool_versions  # noqa: E402


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


DEFAULT_GMRTD_PIN = "64bd6ab"
JMRTD_JAR = "drivers/jmrtd/target/jmrtd-driver-0.1.0.jar"


def ensure_jmrtd_jar(root: Path) -> Path:
    subprocess.check_call(["bash", str(root / "scripts/install-jmrtd-local.sh")], cwd=root)
    mvn = shutil.which("mvn") or "mvn"
    subprocess.check_call([mvn, "-q", "-DskipTests", "package"], cwd=root / "drivers/jmrtd")
    jar = root / JMRTD_JAR
    if not jar.is_file():
        raise SystemExit(f"JMRTD driver jar not built: {jar}")
    return jar


JMRTD050_JAR = "drivers/jmrtd050/target/jmrtd050-driver-0.1.0.jar"


def ensure_jmrtd050_jar(root: Path) -> Path:
    """JMRTD 0.5.0 history point: its own module (scuba 0.0.4, bcprov-jdk15on 1.51)."""
    mvn = shutil.which("mvn") or "mvn"
    subprocess.check_call([mvn, "-q", "-DskipTests", "package"], cwd=root / "drivers/jmrtd050")
    jar = root / JMRTD050_JAR
    if not jar.is_file():
        raise SystemExit(f"JMRTD 0.5.0 driver jar not built: {jar}")
    return jar


def build_go_bins(root: Path, builds: set[tuple[str, str]]) -> dict[tuple[str, str], Path]:
    """Build each (command, gmrtd pin) once. Non-default pins use their own module file and tag."""
    bindir = root / "bin"
    bindir.mkdir(exist_ok=True)
    out: dict[tuple[str, str], Path] = {}
    for cmd, pin in sorted(builds):
        dest = bindir / (f"{cmd}-{pin}" + (".exe" if sys.platform == "win32" else ""))
        args = ["go", "build", "-o", str(dest)]
        if pin != DEFAULT_GMRTD_PIN:
            args += [f"-modfile=gomod/gmrtd-{pin}.mod", f"-tags=gmrtd_{pin}"]
        subprocess.check_call(args + [f"./cmd/{cmd}"], cwd=root)
        out[(cmd, pin)] = dest
    return out


DOTNET_DLL = "drivers/dotnet/bin/out/EmrtdDotnetRead.dll"


DART_EXE = "drivers/dart/build/dmrtd_read"


def ensure_chip_serve(root: Path) -> Path:
    """The harness chip over the vpcd socket, for drivers in other languages."""
    chip = root / "bin" / ("chip-serve" + (".exe" if sys.platform == "win32" else ""))
    chip.parent.mkdir(exist_ok=True)
    subprocess.check_call(["go", "build", "-o", str(chip), "./cmd/chip-serve"], cwd=root)
    return chip


def ensure_dotnet_driver(root: Path) -> Path:
    dotnet = shutil.which("dotnet") or "dotnet"
    subprocess.check_call(
        [dotnet, "build", "drivers/dotnet", "-c", "Release", "-o", "drivers/dotnet/bin/out", "-nologo", "-v", "q"],
        cwd=root,
    )
    return root / DOTNET_DLL


def ensure_dart_driver(root: Path) -> Path:
    dart = shutil.which("dart") or "dart"
    subprocess.check_call([dart, "pub", "get"], cwd=root / "drivers/dart", stdout=subprocess.DEVNULL)
    (root / DART_EXE).parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call([dart, "compile", "exe", "bin/dmrtd_read.dart", "-o", "build/dmrtd_read"],
                          cwd=root / "drivers/dart", stdout=subprocess.DEVNULL)
    return root / DART_EXE


def run_dart(exe: Path, chip: Path, log_dir: Path, flags: list[str]) -> None:
    subprocess.check_call([str(exe), "-chip-serve", str(chip), "-log-dir", str(log_dir), *flags], cwd=ROOT)


def run_dotnet(dll: Path, chip: Path, log_dir: Path, flags: list[str]) -> None:
    dotnet = shutil.which("dotnet") or "dotnet"
    subprocess.check_call([dotnet, str(dll), "-chip-serve", str(chip), "-log-dir", str(log_dir), *flags], cwd=ROOT)


def common_flags(entry: dict, manifest: dict, profile: Path, i: int, n: int) -> list[str]:
    return [
        "-profile",
        str(profile),
        "-suite-id",
        manifest["suite_id"],
        "-suite-seed",
        str(manifest.get("seed", 1)),
        "-suite-n",
        str(n),
        "-run-index",
        str(i),
        "-variant",
        entry["variant"],
    ]


def go_flags(entry: dict) -> list[str]:
    flags = []
    if entry.get("allow_bac_fallback"):
        flags.append("-allow-bac-fallback")
    if entry.get("guard"):
        flags.append("-guard")
    return flags


def run_go(bin_path: Path, log_dir: Path, flags: list[str]) -> None:
    subprocess.check_call([str(bin_path), "-log-dir", str(log_dir), *flags], cwd=ROOT)


def run_java(jar: Path, log_dir: Path, flags: list[str]) -> None:
    subprocess.check_call(["java", "-jar", str(jar), "-log-dir", str(log_dir), *flags], cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run harness suite from JSON manifest")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, default=None)
    parser.add_argument("--n", type=int, default=None, help="override manifest n")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    suite_id = manifest["suite_id"]
    default_n = int(manifest.get("n", SUITE_N_DEFAULT))
    n_override = args.n

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = args.log_dir or (ROOT / "logs" / f"suite-{suite_id}-{ts}")
    log_dir.mkdir(parents=True, exist_ok=True)

    go_builds = {
        (e["command"], e.get("gmrtd_pin", DEFAULT_GMRTD_PIN)) for e in manifest["entries"] if e["driver"] == "go"
    }
    go_bins = build_go_bins(ROOT, go_builds) if go_builds else {}
    jmrtd_jar = ensure_jmrtd_jar(ROOT) if any(e["driver"] == "java" for e in manifest["entries"]) else None
    jmrtd050_jar = ensure_jmrtd050_jar(ROOT) if any(e["driver"] == "java050" for e in manifest["entries"]) else None
    drivers = {e["driver"] for e in manifest["entries"]}
    chip_serve = ensure_chip_serve(ROOT) if drivers & {"dotnet", "dart", "java", "java050"} else None
    dotnet_dll = ensure_dotnet_driver(ROOT) if "dotnet" in drivers else None
    dart_exe = ensure_dart_driver(ROOT) if "dart" in drivers else None

    env_path = log_dir / "environment.json"
    env_path.write_text(json.dumps(tool_versions(ROOT), indent=2) + "\n", encoding="utf-8")

    expected = 0
    for entry in manifest["entries"]:
        n = int(entry.get("n", n_override if n_override is not None else default_n))
        profile = ROOT / entry["profile"]
        driver = entry["driver"]

        for i in range(1, n + 1):
            expected += 1
            flags = common_flags(entry, manifest, profile, i, n)
            if driver == "go":
                pin = entry.get("gmrtd_pin", DEFAULT_GMRTD_PIN)
                run_go(go_bins[(entry["command"], pin)], log_dir, flags + go_flags(entry))
            elif driver == "java":
                assert jmrtd_jar is not None and chip_serve is not None
                run_java(jmrtd_jar, log_dir, flags + ["-integrator", entry["integrator"], "-chip-serve", str(chip_serve)])
            elif driver == "java050":
                assert jmrtd050_jar is not None and chip_serve is not None
                run_java(jmrtd050_jar, log_dir, flags + ["-chip-serve", str(chip_serve)])
            elif driver == "dotnet":
                assert dotnet_dll is not None and chip_serve is not None
                run_dotnet(dotnet_dll, chip_serve, log_dir, flags)
            elif driver == "dart":
                assert dart_exe is not None and chip_serve is not None
                run_dart(dart_exe, chip_serve, log_dir, flags)
            else:
                raise SystemExit(f"unknown driver: {driver}")

    skip_names = {"artifact-manifest.json", "environment.json"}
    actual = len([
        p for p in log_dir.glob("*.json")
        if p.name not in skip_names and not p.name.startswith("summary")
    ])
    if actual != expected:
        print(f"error: expected {expected} artifacts, found {actual}", file=sys.stderr)
        return 1

    agg = subprocess.run(
        [
            sys.executable,
            str(ROOT / "classifier/aggregate.py"),
            "--log-dir",
            str(log_dir),
            "--manifest",
            str(args.manifest),
            "--suite-id",
            suite_id,
            "--suite-seed",
            str(manifest.get("seed", 1)),
        ],
        cwd=ROOT,
        check=False,
    )
    if agg.returncode != 0:
        return agg.returncode

    print(f"SUITE OK — {actual} runs under {log_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
