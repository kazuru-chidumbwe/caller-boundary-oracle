"""Caller-boundary oracle (same predicate as classifier/observability.go and Observability.java).

A driver injects a failure into one negotiation or authentication step, calls the library
API the way an integrator would, and records four events visible at the API boundary.
``classify`` maps them to an outcome; testdata/observability-vectors.json keeps the three
implementations aligned.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Outcome(str, Enum):
    SILENT = "silent"
    STATUS_ONLY = "status_only"
    SURFACED = "surfaced"
    NOT_APPLICABLE = "not_applicable"
    INVALID = "invalid"

    @property
    def score(self) -> Optional[int]:
        return _SCORES.get(self)


_SCORES = {Outcome.SILENT: 0, Outcome.STATUS_ONLY: 1, Outcome.SURFACED: 2}

SCORED_OUTCOMES = (Outcome.SILENT, Outcome.STATUS_ONLY, Outcome.SURFACED)


FIELDS = ("fired", "failed", "succeeded", "returned_error", "status_signal")


@dataclass(frozen=True)
class Observation:
    """``fired`` comes from the harness; the other fields from the library and caller code."""

    fired: bool
    failed: bool
    succeeded: bool
    returned_error: bool
    status_signal: bool

    @classmethod
    def from_dict(cls, d: dict) -> "Observation":
        return cls(*(bool(d[k]) for k in FIELDS))


def classify(o: Observation) -> Outcome:
    """Invalid and not-applicable are decided before any score is assigned."""
    if o.failed and o.succeeded:
        return Outcome.INVALID
    if not o.fired:
        return Outcome.NOT_APPLICABLE
    if o.returned_error:
        return Outcome.SURFACED
    if o.status_signal:
        return Outcome.STATUS_ONLY
    return Outcome.SILENT
