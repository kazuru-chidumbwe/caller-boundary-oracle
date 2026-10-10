#!/usr/bin/env python3
"""Verify canonical artifact-manifest.json — CI gate for make paper."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from constants import ARTIFACT_MANIFEST_VERSION, METHODOLOGY_NOTE  # noqa: E402
from schema_validate import (  # noqa: E402
    SchemaUnavailableError,
    validate_artifact_manifest,
    validate_run_artifact,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


RUN_SKIP_NAMES = {"artifact-manifest.json", "environment.json"}


def run_files(log_dir: Path) -> set[str]:
    return {
        p.name
        for p in log_dir.glob("*.json")
        if p.name not in RUN_SKIP_NAMES and not p.name.startswith("summary")
    }


def check_run_coverage(log_dir: Path, manifest: dict) -> list[str]:
    """Every run on disk is in per_run and in exactly one finding; counts agree."""
    errors: list[str] = []
    on_disk = run_files(log_dir)
    per_run = [r.get("path") for r in manifest.get("per_run") or []]
    if len(per_run) != len(set(per_run)):
        errors.append("per_run lists a run more than once")
    if set(per_run) != on_disk:
        missing = sorted(on_disk - set(per_run))[:5]
        extra = sorted(set(per_run) - on_disk)[:5]
        errors.append(f"per_run does not match run files on disk (missing {missing}, extra {extra})")

    for rec in manifest.get("per_run") or []:
        path = log_dir / (rec.get("path") or "")
        if path.is_file() and sha256_file(path) != rec.get("sha256"):
            errors.append(f"per_run sha256 mismatch: {rec.get('path')}")

    seen: dict[str, str] = {}
    total = 0
    for key, entry in manifest.get("entries", {}).items():
        if entry.get("type") != "finding":
            continue
        refs = entry.get("artifact_refs", [])
        n = entry.get("observation", {}).get("n")
        if n != len(refs):
            errors.append(f"{key}: observation.n={n} but {len(refs)} artifact_refs")
        total += len(refs)
        for ref in refs:
            if ref in seen:
                errors.append(f"{ref} counted in both {seen[ref]} and {key}")
            seen[ref] = key
    if total != len(on_disk):
        errors.append(f"findings cover {total} runs but {len(on_disk)} run files exist")
    return errors


HELD_OUT_MISMATCHES: list[str] = []


def check_expected_outcomes(log_dir: Path, manifest: dict, spec: dict) -> list[str]:
    """Suite entries pin ``expect_outcome``: one outcome, a list of allowed outcomes, or
    {gmrtd commit prefix: outcome}."""
    errors: list[str] = []
    expect_by_scenario = {
        e["scenario_id"]: e["expect_outcome"]
        for e in spec.get("entries", [])
        if "expect_outcome" in e and "scenario_id" in e
    }
    held_out = {e["scenario_id"] for e in spec.get("entries", []) if e.get("held_out") and "scenario_id" in e}
    if not expect_by_scenario:
        return errors
    checked: set[str] = set()
    for rec in manifest.get("per_run") or []:
        scenario = rec.get("scenario_id")
        if scenario not in expect_by_scenario:
            continue
        want = expect_by_scenario[scenario]
        run_path = log_dir / rec["path"]
        if not run_path.is_file():
            continue  # reported by check_run_coverage
        if isinstance(want, dict):
            run_obj = json.loads(run_path.read_text(encoding="utf-8"))
            pin = (run_obj.get("provenance") or {}).get("gmrtd_commit") or ""
            matches = [v for k, v in want.items() if pin.startswith(k)]
            if not matches:
                errors.append(f"{scenario}: no expect_outcome for gmrtd commit {pin!r}")
                continue
            want = matches[0]
        got = rec.get("outcome")
        allowed = want if isinstance(want, list) else [want]
        if got not in allowed:
            msg = f"{scenario}: expected {' or '.join(allowed)}, got {got} ({rec['path']})"
            if scenario in held_out:
                HELD_OUT_MISMATCHES.append(msg)   # a prediction that did not hold: a result, not a harness fault
            else:
                errors.append(msg)
        checked.add(scenario)
    for scenario in sorted(set(expect_by_scenario) - checked):
        errors.append(f"{scenario}: expect_outcome set but no run found")

    expect_obs = {
        e["scenario_id"]: e["expect_observation"]
        for e in spec.get("entries", [])
        if "expect_observation" in e and "scenario_id" in e
    }
    for rec in manifest.get("per_run") or []:
        want = expect_obs.get(rec.get("scenario_id"))
        run_path = log_dir / rec["path"]
        if not want or not run_path.is_file():
            continue
        observation = json.loads(run_path.read_text(encoding="utf-8")).get("observation") or {}
        for field, value in want.items():
            if observation.get(field) != value:
                errors.append(f"{rec['scenario_id']}: observation.{field}={observation.get(field)!r}, expected {value!r}")
    return errors


def verify(
    log_dir: Path,
    suite_manifest: Path | None,
    *,
    skip_schema: bool = False,
    check_pipeline: bool = True,
) -> list[str]:
    errors: list[str] = []
    manifest_path = log_dir / "artifact-manifest.json"
    if not manifest_path.is_file():
        return ["missing artifact-manifest.json (canonical object)"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if not skip_schema:
        try:
            for msg in validate_artifact_manifest(manifest):
                errors.append(f"schema artifact-manifest: {msg}")
        except SchemaUnavailableError as e:
            errors.append(str(e))

    if manifest.get("artifact_version") != ARTIFACT_MANIFEST_VERSION:
        errors.append(f"artifact_version must be {ARTIFACT_MANIFEST_VERSION}")

    if manifest.get("methodology_note") != METHODOLOGY_NOTE:
        errors.append("methodology_note does not match frozen constants.py text")

    if check_pipeline:
        if manifest.get("harness_dirty"):
            errors.append("harness_dirty=true — release artifacts require a clean checkout")

        pipeline = manifest.get("pipeline", {})
        for gate in ("tests", "smoke"):
            if pipeline.get(gate) != "pass":
                errors.append(f"pipeline gate failed or missing: {gate}={pipeline.get(gate)!r}")
        if pipeline.get("suite_complete") is not True:
            errors.append(f"pipeline gate failed or missing: suite_complete={pipeline.get('suite_complete')!r}")

    entries = manifest.get("entries", {})
    errors.extend(check_run_coverage(log_dir, manifest))

    if suite_manifest and suite_manifest.is_file():
        spec = json.loads(suite_manifest.read_text(encoding="utf-8"))
        errors.extend(check_expected_outcomes(log_dir, manifest, spec))
        expected_figs = [
            e["figure_id"]
            for e in spec.get("entries", [])
            if e.get("figure_id", "").startswith("FIG-")
        ]
        for fig in expected_figs:
            if fig not in entries:
                errors.append(f"missing manifest entry for {fig}")

    for key, entry in entries.items():
        if entry.get("type") == "finding":
            for ref in entry.get("artifact_refs", []):
                p = log_dir / ref
                if not p.is_file():
                    errors.append(f"{key}: missing run artifact {ref}")
        elif entry.get("type") in ("table", "summary", "manifest"):
            p = log_dir / entry.get("path", "")
            if not p.is_file():
                errors.append(f"{key}: missing file {entry.get('path')}")
            elif entry.get("type") == "manifest":
                m2 = dict(manifest)
                e2 = dict(entries)
                e2.pop("MANIFEST-01", None)
                m2["entries"] = e2
                expected = hashlib.sha256((json.dumps(m2, indent=2) + "\n").encode()).hexdigest()
                if expected != entry.get("sha256"):
                    errors.append(f"{key}: manifest self-hash mismatch")
            elif sha256_file(p) != entry.get("sha256"):
                errors.append(f"{key}: sha256 mismatch for {entry.get('path')}")

    if "TABLE-01" not in entries:
        errors.append("missing TABLE-01 entry")
    if "MANIFEST-01" not in entries:
        errors.append("missing MANIFEST-01 self-reference")

    # Schema-check per-run JSON listed in the manifest (bounded sample if huge)
    if not skip_schema:
        per_run = manifest.get("per_run") or []
        for rec in per_run:
            rel = rec.get("path")
            if not rel:
                continue
            run_path = log_dir / rel
            if not run_path.is_file():
                errors.append(f"per_run missing file: {rel}")
                continue
            try:
                run_obj = json.loads(run_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                errors.append(f"per_run JSON error {rel}: {e}")
                continue
            try:
                for msg in validate_run_artifact(run_obj):
                    errors.append(f"schema run {rel}: {msg}")
                hc = (run_obj.get("provenance") or {}).get("harness_commit")
                if hc in ("", None):
                    errors.append(f"provenance harness_commit empty: {rel}")
                elif hc == "unknown":
                    # Soft gate: paper deposits should carry a real rev-parse HEAD
                    print(f"VERIFY WARN: harness_commit=unknown in {rel}", file=sys.stderr)
            except SchemaUnavailableError as e:
                errors.append(str(e))
                break

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log_dir", type=Path)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Skip JSON Schema validation (not for paper/CI gates)",
    )
    parser.add_argument(
        "--no-pipeline",
        action="store_true",
        help="Skip pipeline-state and clean-checkout checks (CI suite runs outside make paper)",
    )
    args = parser.parse_args()

    errors = verify(
        args.log_dir,
        args.manifest,
        skip_schema=args.skip_schema,
        check_pipeline=not args.no_pipeline,
    )
    if HELD_OUT_MISMATCHES:
        (args.log_dir / "held-out-mismatches.txt").write_text("\n".join(HELD_OUT_MISMATCHES) + "\n", encoding="utf-8")
        for m in HELD_OUT_MISMATCHES:
            print(f"HELD-OUT MISMATCH: {m}")
    if errors:
        for e in errors:
            print(f"VERIFY FAIL: {e}", file=sys.stderr)
        return 1
    print(f"VERIFY OK — {args.log_dir / 'artifact-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
