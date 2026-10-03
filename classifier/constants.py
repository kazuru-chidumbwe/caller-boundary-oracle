"""Frozen schema version constants — bump only with explicit migration."""

# Tip classifier constants. Citable locked-run evidence: Release v1.0.12.

ARTIFACT_MANIFEST_VERSION = 1
PROVENANCE_VERSION = 1
RUN_ARTIFACT_VERSION = 1

METHODOLOGY_NOTE = (
    "In-process simulators are deterministic (no RNG, no concurrency). "
    "Each profile is therefore run at N=1; multi-profile cells (e.g. the 50-profile "
    "AC-01 sweep) establish consistency across profiles, not repeated identical trials. "
    "The ≥95% finding threshold applies only to multi-profile cells (n ≥ 2); "
    "single-profile cells are reported with the threshold marked not applicable."
)

FINDING_THRESHOLD_PCT = 95.0
FINDING_MIN_N = 2
SUITE_N_DEFAULT = 1
