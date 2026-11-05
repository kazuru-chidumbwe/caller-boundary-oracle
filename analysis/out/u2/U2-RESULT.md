# U2 result: passauf v0.2.1 on the held-out cells

Harness cc5ecb696b3b78f21c1e9363792ac41df2c4d258 (clean); passauf 05098d8 (v0.2.1); rustc 1.92.0; Testbed A, 5 Nov 2026.
Suite `suites/heldout-passauf-v021.json`: the 49 entries of the v0.2.0 held-out suite, driver source unchanged,
expectations from the v0.2.1 source committed before the run (c9acb4a).

| | |
| --- | --- |
| runs | 148 |
| cells as pre-registered | 48 of 48 |
| runs as pre-registered | 148 of 148 |
| hangs | 0 |
| outcomes | not_applicable 104, status_only 38, surfaced 6 |

The two v0.2.0 defects are gone in v0.2.1:

- No-response cells (D9): `read_document` returns `SessionError::CardLost` (passauf 73e9384, fixes #17), so the
  caller receives an error. Surfaced, no panic.
- `PACE-mse-set-at-6c00` (D8): passauf resends once and then takes its PACE fallback to BAC (53b3650, fixes #16).
  Status-only, as pre-registered for v0.2.0; no resend loop.

Every other entry has the v0.2.0 outcome. Source: `COMPARE.json` (per-cell comparison against the manifest),
`environment.json`.
