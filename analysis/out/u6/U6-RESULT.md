# U6 result: JMRTD 0.8.9, PACE step 4 answered 9000 with a changed body

Harness b82b3d8fb63ea0f926e13ebd8c4b7912ff0a459e (clean before and after); JMRTD 0.8.9 (driver jar built at that
commit); independent chip (vsmartcard and OpenPACE, `tools/vsmartcard/emrtd_card.py`, `ga4_body`); OpenJDK 21.0.12.1;
Testbed A, 5 Nov 2026. Suite `suites/u6-jmrtd.json`, expectations in `profiles/generate_u6_profiles.py`, both
committed before the run. Verification: SUITE OK, VERIFY OK, 10 of 10 as pre-registered.

The chip runs the real PACE step 4 (it checks the reader's token and switches to the session keys) and then answers
9000 with the body below.

| body | integrator | outcome | PACE reported | what the caller sees |
| --- | --- | --- | --- | --- |
| empty-7c (`7C00`) | propagate | silent | succeeded | EF.COM read over PACE, no error |
| empty-7c | catch-continue | silent | succeeded | EF.COM read over PACE, no error |
| truncated-86 (`7C04 8608` + 2 bytes) | propagate | silent | succeeded | EF.COM read over PACE, no error |
| truncated-86 | catch-continue | silent | succeeded | EF.COM read over PACE, no error |
| wrong-token (full length, inverted) | propagate | surfaced | failed | CardServiceProtocolException, PACE step 4 |
| wrong-token | catch-continue | surfaced | failed | BAC fallback refused by the chip (6985) |
| no-data | propagate | surfaced | failed | CardServiceProtocolException, PACE step 4 |
| no-data | catch-continue | surfaced | failed | BAC fallback refused by the chip (6985) |
| none (positive control) | propagate | not_applicable | succeeded | EF.COM read |
| none (positive control) | catch-continue | not_applicable | succeeded | EF.COM read |

Reading. In `PACEProtocol.doPACEStep4` an `IOException` while parsing the step-4 body is logged at WARNING and the
method returns null, the value a Generic or Integrated Mapping step 4 returns on success. The comparison of the
chip's authentication token with the expected one is never reached, and `doPACE` completes. A chip that answers
step 4 without a usable token therefore passes PACE in JMRTD, and the failure appears only in the library's log.
A full-length wrong token is caught, so the defect is the parse path, not the comparison. In this cell the session
keys are right because the chip completed step 4; the secure-messaging MAC is what still binds later responses
to the PACE key.

Doc 9303 Part 11 (PACE, step 4) has the terminal verify the chip's authentication token; the run shows JMRTD
completing PACE without that verification on two malformed bodies.

Source: `u6-results.json` (outcome fields per run), `summary.md`, `environment.json`. Raw run files with the APDU
trace stay on Testbed A (`~/cbo/u6-run`).
