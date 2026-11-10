#!/usr/bin/env python3
"""Build the canonical artifact manifest (v1) — primary published object."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from constants import (
    ARTIFACT_MANIFEST_VERSION,
    FINDING_MIN_N,
    FINDING_THRESHOLD_PCT,
    METHODOLOGY_NOTE,
    PROVENANCE_VERSION,
    RUN_ARTIFACT_VERSION,
)
from observability import SCORED_OUTCOMES, Observation, Outcome, classify


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bundle_sha256(hashes: list[str]) -> str:
    return hashlib.sha256("".join(sorted(hashes)).encode("utf-8")).hexdigest()


def run_key(item: dict) -> tuple[str, str, str]:
    """Identify the suite entry a run came from (one entry = one profile x library x variant)."""
    return (
        item.get("test_case", ""),
        item.get("library", ""),
        item.get("variant", "baseline"),
    )


def cell_key(run: dict, suite_entry: dict) -> tuple[str, str, str]:
    """Aggregation cell: entries sharing a ``cell`` id (e.g. a 50-profile sweep) pool together.

    Without an explicit ``cell`` the entry's test case is the cell, so single-profile
    suites keep one cell per test case.
    """
    cell = suite_entry.get("cell") or run.get("test_case", "")
    return (cell, run.get("library", ""), run.get("variant", "baseline"))


def run_outcome(run: dict) -> Outcome:
    """Recompute the outcome from the recorded observation and check the driver agreed."""
    outcome = classify(Observation.from_dict(run["observation"]))
    if run.get("outcome") != outcome.value:
        raise ValueError(f"{run.get('run_id')}: driver outcome {run.get('outcome')!r} != oracle {outcome.value!r}")
    if run.get("observability_score") != outcome.score:
        raise ValueError(f"{run.get('run_id')}: score {run.get('observability_score')!r} != {outcome.score!r}")
    return outcome


def behaviour_signature(run: dict, outcome: Outcome) -> str:
    """Caller-visible behaviour: outcome, the five observation flags and the injection point.

    Status words and error text are deliberately left out: they change what the error says,
    not whether or how the caller learns about the failure.
    """
    obs = run["observation"]
    flags = "".join(
        "1" if obs[k] else "0" for k in ("fired", "failed", "succeeded", "returned_error", "status_signal")
    )
    return f"{outcome.value}|{flags}|{run.get('fault_point', '')}"


def _profiles(group_runs: list[dict]) -> list[dict]:
    seen: dict[tuple[str, str], None] = {}
    for run in group_runs:
        prov = run.get("provenance", {})
        seen.setdefault((prov.get("profile_path") or "", prov.get("profile_sha256") or ""), None)
    return [{"path": path, "sha256": digest} for path, digest in sorted(seen)]


def build_manifest(
    *,
    log_dir: Path,
    runs: list[dict],
    suite_id: str,
    suite_seed: int,
    suite_manifest: dict | None,
    pipeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry_by_key: dict[tuple[str, str, str], dict] = {}
    if suite_manifest:
        for entry in suite_manifest.get("entries", []):
            key = run_key(entry)
            if key in entry_by_key:
                # A held-out manifest gathers one entry from several source suites (a single run and a repeat
                # series of the same profile). Runs cannot be told apart, so such entries pool into one cell;
                # this is only sound when they make the same claim.
                prev = entry_by_key[key]
                same = all(prev.get(f) == entry.get(f) for f in ("profile", "expect_outcome"))
                if not same or prev.get("source_suite") == entry.get("source_suite"):
                    raise ValueError(f"duplicate suite entry for {key}")
                continue
            entry_by_key[key] = entry

    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for run in runs:
        groups[cell_key(run, entry_by_key.get(run_key(run), {}))].append(run)

    commits = {r.get("provenance", {}).get("harness_commit", "unknown") for r in runs}
    if len(commits) > 1:
        raise ValueError(f"runs come from several harness commits: {sorted(commits)}")
    commit = commits.pop() if commits else "unknown"
    harness_dirty = any(r.get("provenance", {}).get("harness_dirty", False) for r in runs)

    entries: dict[str, Any] = {}
    per_run_records: list[dict] = []

    for key, group_runs in sorted(groups.items()):
        cell, library, variant = key
        sample = group_runs[0]
        suite_entries = [entry_by_key.get(run_key(r), {}) for r in group_runs]
        fig_ids = {e.get("figure_id") or r.get("figure_id") for e, r in zip(suite_entries, group_runs)}
        fig_ids.discard(None)
        fig_ids.discard("")
        if len(fig_ids) > 1:
            raise ValueError(f"cell {key} spans several figure ids: {sorted(fig_ids)}")
        fig_id = fig_ids.pop() if fig_ids else f"CELL-{cell}-{library}-{variant}"
        if fig_id in entries:
            raise ValueError(f"manifest key collision: {fig_id} (cell {key})")
        manifest_entry = suite_entries[0]
        scenario_id = (
            manifest_entry.get("scenario_id", f"SCN-{cell}-{library}-{variant}")
            if len(group_runs) == 1
            else f"SCN-{cell}-{library}-{variant}"
        )

        outcomes = [run_outcome(r) for r in group_runs]
        n = len(outcomes)
        counts = {o.value: outcomes.count(o) for o in Outcome}
        scored = [o for o in outcomes if o in SCORED_OUTCOMES]
        n_scored = len(scored)
        pct = {
            o.value: round(100.0 * scored.count(o) / n_scored, 2) if n_scored else 0.0
            for o in SCORED_OUTCOMES
        }
        dominant = max(SCORED_OUTCOMES, key=lambda o: scored.count(o)) if n_scored else None
        dominant_pct = pct[dominant.value] if dominant else 0.0

        classes: dict[str, dict] = {}
        for run, outcome in zip(group_runs, outcomes):
            sig = behaviour_signature(run, outcome)
            cls = classes.setdefault(sig, {"signature": sig, "count": 0, "example_run": run["run_id"]})
            cls["count"] += 1

        artifact_refs: list[str] = []
        run_hashes: list[str] = []
        for run, run_entry in zip(group_runs, suite_entries):
            fname = f"{run['run_id']}.json"
            fpath = log_dir / fname
            fh = sha256_file(fpath)
            run_hashes.append(fh)
            artifact_refs.append(fname)
            per_run_records.append(
                {
                    "run_id": run["run_id"],
                    "path": fname,
                    "sha256": fh,
                    "figure_id": fig_id,
                    "scenario_id": run_entry.get("scenario_id", scenario_id),
                    "outcome": run.get("outcome"),
                    "observability_score": run.get("observability_score"),
                }
            )

        driver = sample.get("provenance", {}).get("driver", manifest_entry.get("command", ""))
        middleware = manifest_entry.get("middleware") or sample.get("provenance", {}).get("middleware")

        entries[fig_id] = {
            "type": "finding",
            "scenario": {
                "id": scenario_id,
                "cell": cell,
                "test_cases": sorted({r.get("test_case", "") for r in group_runs}),
                "library": library,
                "mechanism": sample.get("mechanism", ""),
                "condition": sample.get("condition", ""),
                "variant": variant,
                "tier": sample.get("tier", ""),
                "profiles": _profiles(group_runs),
            },
            "execution": {
                "driver": driver,
                "middleware": middleware,
                "suite_n": n,
            },
            "observation": {
                "n": n,
                "n_scored": n_scored,
                "counts": counts,
                "scored_pct": pct,
                "dominant_outcome": dominant.value if dominant else None,
                "behaviour_classes": sorted(classes.values(), key=lambda c: (-c["count"], c["signature"])),
            },
            "finding": {
                "threshold_pct": FINDING_THRESHOLD_PCT,
                "min_n": FINDING_MIN_N,
                "applicable": n_scored >= FINDING_MIN_N and counts[Outcome.INVALID.value] == 0,
                "met": (
                    n_scored >= FINDING_MIN_N
                    and counts[Outcome.INVALID.value] == 0
                    and dominant_pct >= FINDING_THRESHOLD_PCT
                ),
            },
            "artifact_refs": artifact_refs,
            "bundle_sha256": bundle_sha256(run_hashes),
        }

    return {
        "artifact_version": ARTIFACT_MANIFEST_VERSION,
        "provenance_version": PROVENANCE_VERSION,
        "run_schema_version": RUN_ARTIFACT_VERSION,
        "suite": suite_id,
        "commit": commit,
        "harness_dirty": harness_dirty,
        "suite_seed": suite_seed,
        "generated_at": _utc_now_rfc3339(),
        "methodology_note": METHODOLOGY_NOTE,
        "pipeline": pipeline or {},
        "per_run": per_run_records,
        "entries": entries,
    }


def _utc_now_rfc3339() -> str:
    """Honor SOURCE_DATE_EPOCH when set (reproducible generated_at)."""
    import os

    raw = (os.environ.get("SOURCE_DATE_EPOCH") or "").strip()
    if raw:
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except ValueError:
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def attach_derived_artifacts(
    manifest: dict[str, Any],
    *,
    log_dir: Path,
    summary_json: Path,
    summary_md: Path,
    table_id: str = "TABLE-01",
) -> dict[str, Any]:
    """Attach TABLE/SUMMARY entries only; MANIFEST-01 is hashed in write_canonical_manifest."""
    del log_dir  # reserved for callers that pass staging dir
    manifest = dict(manifest)
    entries = dict(manifest.get("entries", {}))

    entries[table_id] = {
        "type": "table",
        "path": summary_md.name,
        "sha256": sha256_file(summary_md),
        "suite": manifest["suite"],
        "commit": manifest["commit"],
    }
    entries["SUMMARY-01"] = {
        "type": "summary",
        "path": summary_json.name,
        "sha256": sha256_file(summary_json),
        "suite": manifest["suite"],
        "commit": manifest["commit"],
    }
    manifest["entries"] = entries
    return manifest


def write_canonical_manifest(manifest: dict[str, Any], log_dir: Path) -> Path:
    """Write artifact-manifest.json; single MANIFEST-01 self-hash (no sort_keys)."""
    out = log_dir / "artifact-manifest.json"
    entries = dict(manifest.get("entries", {}))
    entries.pop("MANIFEST-01", None)
    manifest = dict(manifest)
    manifest["entries"] = entries
    body = json.dumps(manifest, indent=2) + "\n"
    manifest["entries"]["MANIFEST-01"] = {
        "type": "manifest",
        "path": "artifact-manifest.json",
        "sha256": sha256_text(body),
        "suite": manifest["suite"],
        "commit": manifest["commit"],
    }
    final = json.dumps(manifest, indent=2) + "\n"
    out.write_text(final, encoding="utf-8", newline="\n")
    return out


def markdown_table_from_manifest(manifest: dict[str, Any]) -> str:
    lines = [
        f"<!-- artifact_version={manifest['artifact_version']} suite={manifest['suite']} commit={manifest['commit']} -->",
        "| cell | library | variant | N | silent | status-only | surfaced | n/a | invalid | classes | ≥95% |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for key, entry in sorted(manifest.get("entries", {}).items()):
        if entry.get("type") != "finding":
            continue
        obs = entry["observation"]
        c = obs["counts"]
        if not entry["finding"].get("applicable", True):
            finding = "n/a"
        else:
            finding = "yes" if entry["finding"]["met"] else "no"
        lines.append(
            f"| {key} | {entry['scenario']['library']} | {entry['scenario']['variant']} | {obs['n']} "
            f"| {c['silent']} | {c['status_only']} | {c['surfaced']} | {c['not_applicable']} | {c['invalid']} "
            f"| {len(obs['behaviour_classes'])} | {finding} |"
        )
    lines.append("")
    lines.append(f"Canonical manifest: `artifact-manifest.json` · commit `{manifest['commit']}`")
    lines.append("")
    lines.append(manifest.get("methodology_note", ""))
    return "\n".join(lines) + "\n"
