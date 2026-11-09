"""JSON Schema wiring, plus consistency checks between suites and profiles."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from observability import Outcome  # noqa: E402
from schema_validate import (  # noqa: E402
    SchemaUnavailableError,
    validate_artifact_manifest,
    validate_run_artifact,
)

PROVENANCE = {
    "harness_commit": "deadbeef",
    "harness_dirty": False,
    "profile_path": "profiles/pace/PACE-mse-set-at-6fff.json",
    "profile_sha256": "a" * 64,
    "suite_id": "smoke",
    "suite_seed": 1,
    "suite_n": 1,
    "run_index": 1,
    "driver": "go/gmrtd-read",
    "variant": "64bd6ab-default",
    "captured_at_utc": "2026-10-03T00:00:00Z",
}


def run(score, outcome, fired=True):
    return {
        "run_id": "PACE-mse-set-at-6fff-gmrtd-000001",
        "test_case": "PACE-mse-set-at-6fff",
        "library": "gmrtd",
        "mechanism": "PACE",
        "condition": "pace_fail_then_bac",
        "tier": "wire",
        "variant": "64bd6ab-default",
        "outcome": outcome,
        "observability_score": score,
        "fault_point": "PACE/mse_set_at",
        "observation": {"fired": fired, "failed": True, "succeeded": False, "returned_error": True, "status_signal": True},
        "provenance": dict(PROVENANCE),
    }


class TestSchemas(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            validate_artifact_manifest({"artifact_version": 1})
        except SchemaUnavailableError as e:
            raise unittest.SkipTest(str(e)) from e

    def test_scored_run_valid(self) -> None:
        self.assertEqual(validate_run_artifact(run(2, "surfaced")), [])

    def test_unscored_run_valid(self) -> None:
        self.assertEqual(validate_run_artifact(run(None, "not_applicable", fired=False)), [])

    def test_run_rejects_bad_score(self) -> None:
        self.assertTrue(validate_run_artifact(run(9, "surfaced")))

    def test_run_rejects_unknown_outcome(self) -> None:
        self.assertTrue(validate_run_artifact(run(1, "logged")))

    def test_run_requires_observation(self) -> None:
        r = run(2, "surfaced")
        del r["observation"]
        self.assertTrue(validate_run_artifact(r))

    def test_minimal_manifest_valid(self) -> None:
        manifest = {
            "artifact_version": 1,
            "provenance_version": 1,
            "run_schema_version": 1,
            "suite": "smoke",
            "commit": "deadbeef",
            "harness_dirty": False,
            "methodology_note": "note",
            "pipeline": {"tests": "pass"},
            "entries": {
                "CELL-PACE-gmrtd-64bd6ab-default": {"type": "finding", "artifact_refs": []},
                "TABLE-01": {"type": "table", "path": "summary.md", "sha256": "c" * 64},
                "MANIFEST-01": {"type": "manifest", "path": "artifact-manifest.json", "sha256": "d" * 64},
            },
        }
        self.assertEqual(validate_artifact_manifest(manifest), [])


class TestSuites(unittest.TestCase):
    def test_entries_reference_profiles_and_outcomes(self) -> None:
        outcomes = {o.value for o in Outcome}
        suites = sorted((ROOT / "suites").glob("*.json"))
        self.assertTrue(suites)
        for suite in suites:
            spec = json.loads(suite.read_text(encoding="utf-8"))
            keys = set()
            for e in spec["entries"]:
                with self.subTest(suite=suite.name, scenario=e["scenario_id"]):
                    # real-chip profiles carry a real MRZ and are generated on the run host only (.gitignore)
                    if not e["profile"].startswith("profiles/real/local/"):
                        self.assertTrue((ROOT / e["profile"]).is_file())
                    # the T20 rehearsal's wrong-MRZ cells have no expectations by design: their direct-path
                    # outcomes become the real-chip expectations, and the hub path is compared with the direct path
                    if spec["suite_id"] == "real-rehearsal" and "expect_outcome" not in e:
                        self.assertIn("wrong-mrz", e["test_case"])
                        continue
                    want = e["expect_outcome"]
                    for o in want if isinstance(want, list) else [want]:
                        self.assertIn(o, outcomes)
                    # a held-out manifest gathers entries from several suites; source_suite keeps them apart
                    key = (e["test_case"], e["library"], e["variant"], e.get("source_suite"))
                    self.assertNotIn(key, keys)
                    keys.add(key)


if __name__ == "__main__":
    unittest.main()
