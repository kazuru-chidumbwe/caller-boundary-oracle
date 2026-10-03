"""Shared oracle vectors (Go and Java read the same file)."""

from __future__ import annotations

import itertools
import json
import unittest
from pathlib import Path

from observability import Observation, Outcome, classify

VECTORS = Path(__file__).resolve().parents[1] / "testdata" / "observability-vectors.json"


class TestObservabilityVectors(unittest.TestCase):
    def test_shared_vectors(self) -> None:
        rows = json.loads(VECTORS.read_text(encoding="utf-8"))
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(row["id"]):
                got = classify(Observation.from_dict(row["input"]))
                self.assertEqual(got.value, row["outcome"])
                self.assertEqual(got.score, row["score"])

    def test_total(self) -> None:
        for bits in itertools.product((False, True), repeat=5):
            self.assertIsInstance(classify(Observation(*bits)), Outcome)

    def test_not_fired_is_not_surfaced(self) -> None:
        got = classify(Observation(fired=False, failed=True, succeeded=False, returned_error=True, status_signal=False))
        self.assertIs(got, Outcome.NOT_APPLICABLE)


if __name__ == "__main__":
    unittest.main()
