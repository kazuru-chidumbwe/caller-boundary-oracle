#!/usr/bin/env python3
"""Run the mutation baseline (mutation/DESIGN.md): unmutated reference first, then every mutant.

For each library version the source is copied once into OUT/work; a mutant is applied to that
copy, built outside the harness tree, run on the reduced-suite entries of its step plus the
CONTROL entries, and the file is restored. Every run gets its own log directory, so the scorer
reads one artifact per run. Results are written per mutant (OUT/runs/<mutant>/done.json), so an
interrupted run resumes where it stopped.

The reference run must reproduce the expected outcome of every reduced-suite entry; if it does
not, the script stops before any mutant runs.

Usage (lab):  bash mutation/run.sh [--only gmrtd] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "classifier"))
from run_suite import common_flags, go_flags  # noqa: E402

DEFAULT_PIN = "64bd6ab"
JMRTD_JAR = ROOT / "drivers/jmrtd/target/jmrtd-driver-0.1.0.jar"
CHIP_SERVE = ROOT / "bin" / "chip-serve"
SKIP = {"artifact-manifest.json", "environment.json"}


def log(out: Path, msg: str) -> None:
    line = time.strftime("%Y-%m-%dT%H:%M:%S ") + msg
    print(line, flush=True)
    with (out / "progress.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def sh(cmd: list[str], cwd: Path, timeout: int = 900) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)[-4000:]


class Library:
    """Source copy, build and run for one library version."""

    def __init__(self, name: str, version: str, vendor: Path, out: Path):
        self.name, self.version, self.vendor, self.out = name, version, vendor, out
        src = {"gmrtd": vendor / f"gmrtd-{version}", "jmrtd": vendor / "jmrtd-sources-0.8.9",
               "emrtd-dotnet": vendor / "emrtd-dotnet", "dmrtd": vendor / "dmrtd"}[name]
        self.work = out / "work" / f"{name}-{version}"
        if not self.work.exists():
            shutil.copytree(src, self.work, symlinks=True, ignore=shutil.ignore_patterns(".git", "bin", "obj", ".dart_tool", "build"))
        self.bin = out / "bin" / f"{name}-{version}"
        self.bin.mkdir(parents=True, exist_ok=True)
        self.prepared = False

    # -- one-time preparation of the out-of-tree build -------------------------------------
    def prepare(self) -> None:
        if self.prepared:
            return
        if self.name == "gmrtd":
            base = ROOT / ("go.mod" if self.version == DEFAULT_PIN else f"gomod/gmrtd-{self.version}.mod")
            text = base.read_text(encoding="utf-8")
            lines = [l for l in text.splitlines() if not l.startswith("replace github.com/gmrtd/gmrtd")]
            lines.append(f"replace github.com/gmrtd/gmrtd => {self.work}")
            self.modfile = self.bin / "build.mod"
            self.modfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
            shutil.copy(base.with_suffix(".sum"), self.bin / "build.sum")
        elif self.name == "emrtd-dotnet":
            self.driver = self.out / "dotnet-driver"
            if not self.driver.exists():
                shutil.copytree(ROOT / "drivers/dotnet", self.driver, ignore=shutil.ignore_patterns("bin", "obj"))
        elif self.name == "dmrtd":
            self.driver = self.out / "dart-driver"
            if not self.driver.exists():
                shutil.copytree(ROOT / "drivers/dart", self.driver, ignore=shutil.ignore_patterns(".dart_tool", "build"))
                spec = (self.driver / "pubspec.yaml").read_text(encoding="utf-8")
                spec = spec.replace("path: ../../../_vendor/dmrtd", f"path: {self.work}")
                spec = spec.replace("path: ../../../_vendor/tripledes_nullsafety", f"path: {self.vendor / 'tripledes_nullsafety'}")
                (self.driver / "pubspec.yaml").write_text(spec, encoding="utf-8")
                rc, msg = sh(["dart", "pub", "get", "--offline"], self.driver)
                if rc != 0:
                    rc, msg = sh(["dart", "pub", "get"], self.driver)
                if rc != 0:
                    raise SystemExit("dart pub get failed: " + msg)
        self.prepared = True

    # -- build the current state of the work copy ------------------------------------------
    def build(self, changed: str | None) -> tuple[bool, str]:
        self.prepare()
        if self.name == "gmrtd":
            args = ["go", "build", f"-modfile={self.modfile}"]
            if self.version != DEFAULT_PIN:
                args.append(f"-tags=gmrtd_{self.version}")
            return self._ok(sh(args + ["-o", str(self.bin / "gmrtd-read"), "./cmd/gmrtd-read"], ROOT))
        if self.name == "jmrtd":
            classes = self.bin / "classes"
            shutil.rmtree(classes, ignore_errors=True)
            classes.mkdir()
            if changed is None:
                return True, ""
            return self._ok(sh(["javac", "-nowarn", "-encoding", "UTF-8", "-cp", str(JMRTD_JAR), "-d", str(classes),
                                str(self.work / changed)], ROOT))
        if self.name == "emrtd-dotnet":
            return self._ok(sh(["dotnet", "build", str(self.driver), "-c", "Release", "-o", str(self.bin / "out"),
                                f"-p:EmrtdDotnetDir={self.work}", "-nologo", "-v", "q"], ROOT))
        return self._ok(sh(["dart", "compile", "exe", "bin/dmrtd_read.dart", "-o", str(self.bin / "dmrtd_read")], self.driver))

    @staticmethod
    def _ok(res: tuple[int, str]) -> tuple[bool, str]:
        return res[0] == 0, res[1]

    def command(self, entry: dict, flags: list[str]) -> list[str]:
        if self.name == "gmrtd":
            return [str(self.bin / "gmrtd-read"), *flags, *go_flags(entry)]
        if self.name == "jmrtd":
            cp = f"{self.bin / 'classes'}{os.pathsep}{JMRTD_JAR}"
            return ["java", "-cp", cp, "org.callerboundary.jmrtd.JmrtdRead", *flags,
                    "-integrator", entry["integrator"], "-chip-serve", str(CHIP_SERVE)]
        if self.name == "emrtd-dotnet":
            return ["dotnet", str(self.bin / "out" / "EmrtdDotnetRead.dll"), "-chip-serve", str(CHIP_SERVE), *flags]
        return [str(self.bin / "dmrtd_read"), "-chip-serve", str(CHIP_SERVE), *flags]


def entries_for(reduced: list[dict], library: str, version: str, step: str | None) -> list[dict]:
    out = []
    for e in reduced:
        if e["library"] != library:
            continue
        if library == "gmrtd" and e.get("gmrtd_pin") != version:
            continue
        if step is None or e["step"] in (step, "CONTROL"):
            out.append(e)
    return out


def run_entry(lib: Library, entry: dict, log_dir: Path, timeout: int) -> dict:
    if log_dir.exists():
        shutil.rmtree(log_dir)
    log_dir.mkdir(parents=True)
    flags = common_flags(entry, {"suite_id": "mutation", "seed": 1}, ROOT / entry["profile"], 1, 1)
    flags = ["-log-dir", str(log_dir), *flags]
    t0 = time.time()
    p = subprocess.Popen(lib.command(entry, flags), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        status = "ok" if p.returncode == 0 else "crash"
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
        status = "timeout"
    arts = [a for a in log_dir.glob("*.json") if a.name not in SKIP]
    if status == "ok" and len(arts) != 1:
        status = "no_artifact"
    rec = {"scenario_id": entry["scenario_id"], "status": status, "seconds": round(time.time() - t0, 2),
           "returncode": p.returncode, "tail": (out or b"").decode("utf-8", "replace")[-600:]}
    if len(arts) == 1:
        a = json.loads(arts[0].read_text(encoding="utf-8"))
        rec |= {"artifact": str(arts[0].relative_to(lib.out)), "outcome": a.get("outcome"),
                "observation": a.get("observation"), "access_control": a.get("access_control"),
                "bac_success": a.get("bac_success")}
    return rec


def signature(rec: dict) -> tuple:
    o = rec.get("observation") or {}
    return (rec["status"], rec.get("outcome"), o.get("returned_error"), o.get("status_signal"), rec.get("access_control"), rec.get("bac_success"))


def is_independent(entry: dict) -> bool:
    return "/independent/" in entry["profile"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vendor", type=Path, default=ROOT.parent / "_vendor")
    ap.add_argument("--out", type=Path, default=ROOT.parent / "mutruns")
    ap.add_argument("--only", default=None, help="library name")
    ap.add_argument("--limit", type=int, default=None, help="at most N mutants per library version (smoke test)")
    ap.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    reduced = json.loads((ROOT / "mutation/reduced.json").read_text(encoding="utf-8"))["entries"]
    mutants = [json.loads(l) for l in (ROOT / "mutation/mutants.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    mutants = [m for m in mutants if m["status"] == "ok" and (a.only is None or m["library"] == a.only)]
    groups: dict[tuple[str, str], list[dict]] = {}
    for m in mutants:
        groups.setdefault((m["library"], m["version"]), []).append(m)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    log(a.out, f"start: harness {head}, {len(mutants)} mutants in {len(groups)} library versions")

    for (name, version), ms in sorted(groups.items()):
        lib = Library(name, version, a.vendor, a.out)
        ref_dir = a.out / "runs" / f"REF-{name}-{version}"
        ref_file = ref_dir / "done.json"
        if not ref_file.exists():
            ok, msg = lib.build(None)
            if not ok:
                raise SystemExit(f"reference build failed for {name} {version}: {msg}")
            runs, bad = [], []
            for e in entries_for(reduced, name, version, None):
                r = run_entry(lib, e, ref_dir / e["scenario_id"], a.timeout)
                want = e["expect_outcome"] if isinstance(e["expect_outcome"], list) else [e["expect_outcome"]]
                if r.get("outcome") not in want:
                    bad.append((e["scenario_id"], r.get("outcome"), want, r["status"]))
                runs.append(r)
            if bad:
                (ref_dir / "MISMATCH.json").write_text(json.dumps(bad, indent=1), encoding="utf-8")
                raise SystemExit(f"reference for {name} {version} does not reproduce the expectations: {bad[:3]}")
            ref_file.write_text(json.dumps({"mutant_id": ref_dir.name, "harness": head, "runs": runs}, indent=1), encoding="utf-8")
            log(a.out, f"REF {name} {version}: {len(runs)} runs reproduce the expectations")
        ref = {r["scenario_id"]: r for r in json.loads(ref_file.read_text(encoding="utf-8"))["runs"]}

        todo = ms if a.limit is None else ms[: a.limit]
        for i, m in enumerate(todo, 1):
            mdir = a.out / "runs" / m["mutant_id"]
            if (mdir / "done.json").exists():
                continue
            target = lib.work / m["file"]
            original = target.read_bytes()
            text = original.decode("utf-8", errors="replace")
            if text[m["start"]:m["end"]] != m["original"]:
                result = {"mutant": m, "build": "skipped", "reason": "source does not match the recorded span"}
            else:
                target.write_text(text[: m["start"]] + m["replacement"] + text[m["end"]:], encoding="utf-8", newline="")
                try:
                    ok, msg = lib.build(m["file"])
                    if not ok:
                        result = {"mutant": m, "build": "failed", "build_log": msg}
                    else:
                        runs = []
                        for e in entries_for(reduced, name, version, m["step"]):
                            r = run_entry(lib, e, mdir / e["scenario_id"], a.timeout)
                            if is_independent(e) and signature(r) != signature(ref[e["scenario_id"]]):
                                r2 = run_entry(lib, e, mdir / (e["scenario_id"] + "-rerun"), a.timeout)
                                r["rerun"] = r2
                            runs.append(r)
                        result = {"mutant": m, "build": "ok", "runs": runs}
                finally:
                    target.write_bytes(original)
            mdir.mkdir(parents=True, exist_ok=True)
            (mdir / "done.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
            if i % 25 == 0 or i == len(todo):
                log(a.out, f"{name} {version}: {i}/{len(todo)} mutants done")
        lib.build(None)  # leave the build directory matching the unmutated source
    log(a.out, "finished")


if __name__ == "__main__":
    main()
