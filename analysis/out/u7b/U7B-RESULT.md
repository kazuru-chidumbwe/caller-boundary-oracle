# U7b result: BAC failure on a chip that serves data after it, and on a chip that enforces access control

Harness d5971d0 (clean before and after), Testbed A, 12 Nov 2026, 16:36 to 16:41 CAT. Expectations in
`profiles/generate_u7b_profiles.py`, committed before the run. Verification: SUITE OK, VERIFY OK, 52 of 52 as
predicted. Regression of the default chip at the same commit: independent suite, 325 runs, VERIFY OK.

Why: U7 (`../u7/U7-RESULT.md`) used the independent chip as vsmartcard ships it. The gmrtd maintainer's reply on
issue #572 (11 Nov 2026) and the APDU trace of the U7 gmrtd wrong-MRZ run showed that, after EXTERNAL AUTHENTICATE
was refused (6988), that chip still served EF.SOD, EF.COM and DG1 in plain. A genuine chip refuses plain access to
LDS files with 6982 (security status not satisfied). U7b runs every entry on both chips:

- **serving**: vsmartcard as shipped (the behaviour of a clone or an emulator after a failed BAC);
- **enforcing**: `tools/vsmartcard/emrtd_card.py` with `access_control: "enforce"`, which answers 6982 to a plain
  SELECT of an LDS file and to any plain READ BINARY or READ RECORD of one. MF files (EF.CardAccess, EF.DIR) stay
  readable in plain. Commands with secure messaging pass unchanged.

Both chips have no EF.CardAccess, so every reader uses BAC. Wrong MRZ = document number T22000120 instead of
T22000129; the chip's own refusal of EXTERNAL AUTHENTICATE is the delivered fault (`observe_refusals: "PACE"`).

| library and arm | right MRZ, both chips | wrong MRZ, serving chip | wrong MRZ, enforcing chip |
| --- | --- | --- | --- |
| gmrtd 0.45.0, 1.1.3, 1.3.2 default | not_applicable | **status_only** (read completes, DG1 included; `Session.BacErr` set) | surfaced: `[readEfSod] ReadFile error: [ReadFile] SelectEF error: [SelectEF] Invalid status:6982` |
| gmrtd 1.1.3, 1.3.2 opt-in fallback | not_applicable | **status_only** | surfaced (same error) |
| gmrtd, all three + guard | not_applicable | surfaced | surfaced |
| JMRTD propagate, catch-continue | not_applicable | surfaced | surfaced |
| emrtd-dotnet | not_applicable | surfaced | surfaced |
| dmrtd | not_applicable | surfaced | surfaced |
| passauf | not_applicable | surfaced | surfaced |

Reading:
- The serving chip reproduces U7 exactly (same outcome in every entry).
- On the enforcing chip, gmrtd still records the BAC failure in the session and continues; readEfDir gets file not
  found for EF.DIR inside the eMRTD application (nil error), and the plain SELECT of EF.SOD gets 6982, so
  `ReadDocument` returns an error. The caller is told that a file could not be read, not that access control failed.
- So D11 is: a failed BAC is recorded in the session only and the read continues. On a chip that serves data after a
  failed BAC (a clone or an emulator), the caller gets a complete document without an error; on a genuine chip, the
  read fails later with a misleading error.
- Other cells: in the 325-run independent regression, no status-only or silent run continued after a failed access
  control (PACE failed and BAC did not succeed): 0 runs. Only D11 depends on the chip's behaviour after a failed BAC.

Upstream: reply on gmrtd #572 with the trace, then the pull request the maintainer invited (BAC returns its error;
reader test with EXTERNAL AUTHENTICATE rejected).

Source: `u7b-results.json` (outcome and error per run), `progress.txt`, run records in
`../../data/suite-u7b-bac-20261112T143656Z/`.
