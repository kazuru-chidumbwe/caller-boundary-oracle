#!/usr/bin/env python3
"""T62 runner (mutation/HELD-OUT-T62.md): the frozen mutation design applied to four WebAuthn libraries.

For each library the source is copied once into OUT/work; each mutant is applied to that copy, built against
the WebAuthn arm's driver, run on the cases of its ceremony plus the positive controls in every arm of the
library, and the file is restored. Run records are written in the form mutation/score.py and per_arm.py read
(OUT/runs/REF-<library>-x/done.json, OUT/runs/M1-<mutant>/done.json), so both run unchanged. The unmutated
library first runs the same cases and must reproduce the outcomes of held-out run 0f5983b; otherwise none of
its mutants runs. Results are written per mutant, so an interrupted run resumes.

Observations come from webauthn/run.py (observe), the outcome from the frozen classifier. The output
differential reads acceptance plus the library's top-level verdict field (`established`), as the WebAuthn arm
defines it (Section 5.4); score.access() returns it when present.

Usage (lab): python3 mutation/run_wa_mutants.py --mutants ../t62/mutants.jsonl --out ../t62/runs-root [--only LIB] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webauthn"))
from classifier.observability import Observation, classify  # noqa: E402
import run as warun  # noqa: E402  webauthn/run.py: observe(), STATUS_FIELDS

WA = Path(os.environ.get("WA_BUILD", str(ROOT.parent / "cbo-wa")))   # checkout where the WebAuthn arm's drivers are built
VENDOR = Path(os.environ.get("VENDOR_DIR", str(ROOT.parent / "_vendor")))
DOTNET = VENDOR / "dotnet" / "dotnet"
LOMBOK = Path.home() / ".m2/repository/org/projectlombok/lombok/1.18.38/lombok-1.18.38.jar"
HELDOUT = ROOT / "webauthn/heldout/run-0f5983b/results.jsonl"
ARMS = {"go-webauthn": ["go-webauthn"], "java-webauthn-server": ["java-webauthn-server"],
        "webauthn4j": ["webauthn4j-strict", "webauthn4j-nonstrict"], "fido2-net-lib": ["fido2-net-lib"]}
SRC = {"go-webauthn": "wa-src/go-webauthn", "java-webauthn-server": "wa-src/java-webauthn-server",
       "webauthn4j": "wa-src/webauthn4j", "fido2-net-lib": "wa-src/fido2-net-lib"}
SUB = {"go-webauthn": "", "java-webauthn-server": "webauthn-server-core/src/main/java",
       "webauthn4j": "webauthn4j-core/src/main/java", "fido2-net-lib": "Src/Fido2"}
VERDICT = {"java-webauthn-server": "success", "webauthn4j-strict": None, "webauthn4j-nonstrict": None,
           "go-webauthn": None, "fido2-net-lib": None}   # top-level verdict field where the API has one


def log(out: Path, msg: str) -> None:
    line = time.strftime("%Y-%m-%dT%H:%M:%S ") + msg
    print(line, flush=True)
    with (out / "progress.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def sh(cmd: list[str], cwd: Path, timeout: int = 900, env: dict | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    return p.returncode, (p.stdout + p.stderr)[-4000:]


class Lib:
    def __init__(self, name: str, out: Path):
        self.name, self.out = name, out
        self.work = out / "work" / name
        if not self.work.exists():
            shutil.copytree(VENDOR / SRC[name], self.work, symlinks=True,
                            ignore=shutil.ignore_patterns(".git", "bin", "obj", "build", "target"))
        self.src = self.work / SUB[name]
        self.bin = out / "bin" / name
        self.bin.mkdir(parents=True, exist_ok=True)
        self.prepared = False

    def prepare(self) -> None:
        if self.prepared:
            return
        if self.name == "go-webauthn":
            self.gdir = self.bin / "driver-src"
            if not self.gdir.exists():
                shutil.copytree(WA / "webauthn/drivers/go", self.gdir)
                with (self.gdir / "go.mod").open("a", encoding="utf-8") as f:
                    f.write(f"\nreplace github.com/go-webauthn/webauthn => {self.work}\n")
        elif self.name == "fido2-net-lib":
            self.ddir = self.bin / "driver-src"
            if not self.ddir.exists():
                shutil.copytree(WA / "webauthn/drivers/dotnet", self.ddir, ignore=shutil.ignore_patterns("bin", "obj", "out"))
                proj = self.ddir / "Fido2Driver.csproj"
                text = proj.read_text(encoding="utf-8").replace(
                    '<PackageReference Include="Fido2" Version="4.2.0" />',
                    f'<ProjectReference Include="{self.work}/Src/Fido2/Fido2.csproj" />')
                text = text.replace("<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>", "")
                proj.write_text(text, encoding="utf-8")
                (self.ddir / "packages.lock.json").unlink(missing_ok=True)
        self.prepared = True

    def build(self, changed: str | None) -> tuple[bool, str]:
        self.prepare()
        if self.name == "go-webauthn":
            env = dict(os.environ, GOFLAGS="-mod=mod", PATH="/usr/local/go/bin:" + os.environ["PATH"])
            rc, msg = sh(["go", "build", "-o", str(self.bin / "driver"), "."], self.gdir, env=env)
            return rc == 0, msg
        if self.name == "fido2-net-lib":
            rc, msg = sh([str(DOTNET), "build", str(self.ddir), "-c", "Release", "-o", str(self.bin / "out"),
                          "-nologo", "-v", "q"], self.ddir, timeout=1200)
            return rc == 0, msg
        classes = self.bin / "classes"
        shutil.rmtree(classes, ignore_errors=True)
        classes.mkdir()
        if changed is None:
            return True, ""
        cp = f"{WA}/webauthn/drivers/java/target/webauthn-drivers-1.0.0.jar:{WA}/webauthn/drivers/java/target/lib/*"
        cmd = ["javac", "-nowarn", "-encoding", "UTF-8", "-proc:full", "-cp", f"{cp}:{LOMBOK}",
               "-processorpath", str(LOMBOK), "-d", str(classes), str(self.src / changed)]
        rc, msg = sh(cmd, self.src)
        return rc == 0, msg

    def command(self, arm: str) -> list[str]:
        if self.name == "go-webauthn":
            return [str(self.bin / "driver")]
        if self.name == "fido2-net-lib":
            return [str(DOTNET), str(self.bin / "out" / "Fido2Driver.dll")]
        cp = f"{self.bin / 'classes'}:{WA}/webauthn/drivers/java/target/webauthn-drivers-1.0.0.jar:{WA}/webauthn/drivers/java/target/lib/*"
        if arm == "java-webauthn-server":
            return ["java", "-cp", cp, "org.callerboundary.webauthn.YubicoDriver"]
        return ["java", "-cp", cp, "org.callerboundary.webauthn.Webauthn4jDriver", arm.split("-")[1]]


def is_control(case: str) -> bool:
    return case.endswith("OK") or "-OK-" in case


def run_case(lib: Lib, arm: str, case_dir: Path, timeout: int) -> dict:
    report = json.loads((case_dir / "report.json").read_text(encoding="utf-8"))
    case = report["case"]
    sid = f"{'CTRL-' if is_control(case) else ''}{case}-{lib.name}-{arm}"
    t0 = time.time()
    try:
        p = subprocess.run(lib.command(arm) + [str(case_dir)], capture_output=True, text=True, timeout=timeout)
        lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
        status = "ok" if p.returncode == 0 and lines else "crash"
    except subprocess.TimeoutExpired:
        return {"scenario_id": sid, "status": "timeout", "seconds": round(time.time() - t0, 2)}
    if status != "ok":
        return {"scenario_id": sid, "status": status, "returncode": p.returncode, "tail": (p.stderr or "")[-600:]}
    rec = json.loads(lines[-1])
    obs = warun.observe(arm, report, rec)
    vf = VERDICT.get(arm)
    verdict = rec.get("fields", {}).get(vf) if vf else None
    accepted = not rec["returned_error"] and verdict is not False
    return {"scenario_id": sid, "status": "ok", "seconds": round(time.time() - t0, 2), "case": case,
            "outcome": classify(Observation.from_dict(obs)).value, "observation": obs,
            "established": "accepted" if accepted else "refused-by-verdict", "error_type": rec.get("error_type")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mutants", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args()
    a.out = a.out.resolve()
    (a.out / "runs").mkdir(parents=True, exist_ok=True)
    cases_dir = a.out / "cases"
    if not cases_dir.exists():
        subprocess.run([sys.executable, str(ROOT / "webauthn/authenticator.py"), "--out", str(cases_dir)], check=True)
    cases = sorted(p for p in cases_dir.iterdir() if p.is_dir())
    ceremony = {c.name: json.loads((c / "report.json").read_text(encoding="utf-8"))["ceremony"] for c in cases}
    held = {}
    for l in HELDOUT.read_text(encoding="utf-8").splitlines():
        r = json.loads(l)
        held[(r["library"], r["case"])] = r["outcome"]
    mutants = [json.loads(l) for l in a.mutants.read_text(encoding="utf-8").splitlines() if l.strip()]
    mutants = [m for m in mutants if m["status"] == "ok" and m["library"] in ARMS and (a.only is None or m["library"] == a.only)]
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    log(a.out, f"start: harness {head}, {len(mutants)} mutants")

    def wanted(step: str) -> list[Path]:
        cer = {"REG": {"registration"}, "AUTH": {"authentication"}}.get(step, {"registration", "authentication"})
        return [c for c in cases if ceremony[c.name] in cer]

    for name in ARMS:
        ms = [m for m in mutants if m["library"] == name]
        if not ms:
            continue
        lib = Lib(name, a.out)
        ref_dir = a.out / "runs" / f"REF-{name}-x"
        ref_file = ref_dir / "done.json"
        if not ref_file.exists():
            ok, msg = lib.build(None)
            if not ok:
                raise SystemExit(f"reference build failed for {name}: {msg}")
            runs, bad = [], []
            for arm in ARMS[name]:
                for c in cases:
                    r = run_case(lib, arm, c, a.timeout)
                    want = held.get((arm, r.get("case", c.name)))
                    if r["status"] != "ok" or (want is not None and r["outcome"] != want):
                        bad.append((arm, c.name, want, r.get("outcome"), r["status"]))
                    runs.append(r)
            ref_dir.mkdir(parents=True, exist_ok=True)
            if bad:
                (ref_dir / "MISMATCH.json").write_text(json.dumps(bad, indent=1), encoding="utf-8")
                log(a.out, f"REF {name}: {len(bad)} runs differ from held-out run 0f5983b; its mutants are skipped")
                continue
            ref_file.write_text(json.dumps({"mutant_id": ref_dir.name, "harness": head, "runs": runs}, indent=1), encoding="utf-8")
            log(a.out, f"REF {name}: {len(runs)} runs reproduce held-out run 0f5983b")
        todo = ms if a.limit is None else ms[: a.limit]
        for i, m in enumerate(todo, 1):
            mdir = a.out / "runs" / f"M1-{m['mutant_id']}"   # the M1- prefix is what score.py and per_arm.py glob for
            if (mdir / "done.json").exists():
                continue
            target = lib.src / m["file"]
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
                        runs = [run_case(lib, arm, c, a.timeout) for arm in ARMS[name] for c in wanted(m["step"])]
                        result = {"mutant": m, "build": "ok", "runs": runs}
                finally:
                    target.write_bytes(original)
            mdir.mkdir(parents=True, exist_ok=True)
            (mdir / "done.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
            if i % 25 == 0 or i == len(todo):
                log(a.out, f"{name}: {i}/{len(todo)} mutants done")
        lib.build(None)
    log(a.out, "finished")


if __name__ == "__main__":
    main()
