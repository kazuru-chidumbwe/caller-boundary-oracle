# WebAuthn held-out evaluation: result (8 October 2026)

**The run.** One run on Testbed A, at harness commit `0f5983b`.
- Working tree clean (`run-0f5983b/RUN.json`).
- Oracle `classifier/observability.py` sha256 `e29e03ec...1bb9`, unchanged.
- Arms: the 13 in `drivers-heldout.json`, which are the 7 pinned arms and the 6 held-out arms that built (`RELEASES.json`).
- Cases: the 31 of the fault peer.
- Expectations: `expectations.json`, committed at `26e1d88` before the run. Each held-out entry was derived from the source of its release, with the reason next to it (`write_expectations.py`).

**Verification.** `python3 webauthn/run.py --expectations webauthn/heldout/expectations.json` reported "all outcomes as pre-registered" (`run-0f5983b/VERIFY.txt`).

| | Pairs |
| --- | ---: |
| All (arm, case) pairs run | 403 |
| Held-out pairs (not run during development) | 263 |
| Held-out pairs whose outcome equals the pre-registered expectation | 263 |
| Driver failures | 0 |
| Held-out fault pairs in which the faulted response reached the library unchanged (fired) | 245 of 245 |
| Held-out positive-control pairs accepted | 18 of 18 |

**Outcomes of the 245 held-out fault pairs.** 214 surfaced, 5 status-only, 26 silent.

Silent:

| Fault | Arms |
| --- | --- |
| crossOrigin true, RP not expecting cross-origin (R-XORIG, A-XORIG) | py_webauthn (both releases); simplewebauthn (R-XORIG in both releases, A-XORIG in 13.3.3; 14.0.3 rejects an unexpected topOrigin in authentication); java-webauthn-server 2.10.0; Fido2 4.2.0 (5.0.0-preview.7 rejects both) |
| User handle of another user (A-UH) | py_webauthn, simplewebauthn, webauthn4j (both arms, both releases); the step is left to the caller and the APIs take no user handle |
| Credential not in the allowed list (A-CRED) | py_webauthn, simplewebauthn (both releases); the APIs take no allow list |
| fmt none with a non-empty statement (R-NONESTMT) | java-webauthn-server 2.10.0 |
| BS without BE at registration (R-BS) | go-webauthn v0.17.4 (v0.18.2 rejects it) |
| Packed self-attestation signature over other bytes (R-ASIG) | webauthn4j 0.30.3 non-strict manager, as in 0.31.11 |

Status-only:
- go-webauthn `CloneWarning`: A-CNTEQ on v0.18.2, and A-CNT and A-CNTEQ on v0.17.4.
- simplewebauthn 13.3.3 `verified: false`: R-ASIG and A-SIG.

Files: `run-0f5983b/results.jsonl` (403 rows with the raw driver records), `run-0f5983b/run.log`.
