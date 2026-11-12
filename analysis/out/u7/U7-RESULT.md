# U7 result: access control on a chip without PACE, right and wrong MRZ, every library entry

**Correction (12 Nov 2026):** the independent chip used here served LDS files in plain after the failed BAC, so "no data group was read" below is wrong: gmrtd read EF.SOD, EF.COM and DG1. On a chip that enforces access control gmrtd fails later at EF.SOD (6982). See `../u7b/U7B-RESULT.md`, which reruns U7 on both chips and supersedes this file.


Harness be99fef (clean before and after); independent chip with no EF.CardAccess (`card_access: none`), so every
reader uses BAC; wrong MRZ = document number T22000120 instead of T22000129; the chip's own refusal of EXTERNAL
AUTHENTICATE is the delivered fault (`observe_refusals: "PACE"`, the access-control key the drivers read).
Testbed A, 5 Nov 2026. Expectations in `profiles/generate_u7_profiles.py`, committed before the run.
Verification: SUITE OK, VERIFY OK, 26 of 26 as predicted.

Regression at the same commit (access-control mapping extended to `BacErr`, ledger B.10): pace 416 runs,
controls 26, independent 325, all VERIFY OK; no earlier outcome changed.

| library and arm | right MRZ | wrong MRZ | what the caller gets with the wrong MRZ |
| --- | --- | --- | --- |
| gmrtd 0.45.0, 1.1.3, 1.3.2 default | not_applicable | **status_only** | `ReadDocument` returns no error; `Session.BacErr` holds the BAC failure |
| gmrtd 1.1.3, 1.3.2 opt-in fallback | not_applicable | **status_only** | as default (no PACE to fall back from) |
| gmrtd, all three + guard | not_applicable | surfaced | the guard turns `BacErr` into an error |
| JMRTD propagate, catch-continue | not_applicable | surfaced | `doBAC` throws (the integrator patterns catch only PACE) |
| emrtd-dotnet | not_applicable | surfaced | CardException, EXTERNAL AUTHENTICATE failed |
| dmrtd | not_applicable | surfaced | PassportError from `startSession` |
| passauf | not_applicable | surfaced | SessionError::authentication |

Defect (D11): in gmrtd, `performBac` stores the BAC error in the session and returns nil ("NB errors are just
recorded at this point", reader/reader.go at 8fea245, 64bd6ab, b861835; unchanged in v1.4.0, v1.7.1, v1.8.0 and
main e5fa863). Since 1.1.3 a failed PACE fails closed by default, but a failed BAC on a chip without PACE never
does: the caller receives a document without an error although access control failed and no data group was read.

The chip answered the wrong key with 6988 (vsmartcard's BAC); a real chip typically answers 6300. gmrtd records
either the same way.

Source: `u7-results.json` (outcome fields per run), `summary-and-progress.md`.
