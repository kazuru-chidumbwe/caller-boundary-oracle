# U3 result: fido2-net-lib 4.3.2 beside 4.2.0 on the held-out WebAuthn cases

Harness cc5ecb696b3b78f21c1e9363792ac41df2c4d258 (clean); oracle sha256 e29e03ec...1bb9; Testbed A, 5 Nov 2026.
Expectations from the 4.3.2 source committed before the run (391faeb, `webauthn/heldout/expectations.json`).
Verification: all outcomes as pre-registered (`VERIFY.txt`, 0 mismatches).

| release | cases | surfaced | silent | not_applicable |
| --- | ---: | ---: | ---: | ---: |
| 4.2.0 | 31 | 24 | 4 | 3 |
| 4.3.2 | 31 | 28 | 0 | 3 |

The four cases that change, all silent in 4.2.0 and surfaced (`Fido2VerificationException`) in 4.3.2:

| case | what the authenticator data or client data carries |
| --- | --- |
| R-BS | registration: backup state set without backup eligibility |
| A-BS | authentication: backup state set without backup eligibility |
| R-XORIG | registration: `crossOrigin` true |
| A-XORIG | authentication: `crossOrigin` true |

4.3.2 contains the #690 backport (expectations read from the 4.3.2 source); it closes both checks on the stable line.
Source: `results.jsonl` (one record per release and case), `RUN.json` (commit, oracle hash, driver builds).
